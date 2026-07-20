#!/usr/bin/env python
"""Test de montée en charge de l'endpoint /data : débit max soutenable.

Contrairement à `benchmark.py` (qui mesure la latence en séquentiel, une
requête à la fois), ce script mesure le **débit** sous charge concurrente.

Principe (boucle fermée) : pour chaque niveau de concurrence C, on lance C
« utilisateurs virtuels » en parallèle ; chacun envoie des requêtes en rafale
(une nouvelle dès que la précédente répond) pendant `--duration` secondes.
On mesure alors :
  - le débit atteint (requêtes/seconde = requêtes terminées / temps écoulé),
  - la latence médiane / p95 / max,
  - le taux d'erreurs (timeouts, 5xx, statuts non-2xx).

En montant C, le débit augmente jusqu'à ce que le serveur sature (CPU) : au-delà,
le débit plafonne et la latence grimpe. Le « débit max soutenable » retenu est
le débit le plus élevé observé tant que la p95 reste sous `--p95-threshold` et
que le taux d'erreurs reste ~nul.

AVERTISSEMENT : ceci met de la charge réelle sur la cible. Chaque requête
compte dans la consommation du token et génère un event Matomo. Ne pas lancer
pendant un déploiement de test.colibre.fr.

Usage :
    python tests/api/loadtest.py --token colibre_xxx
    python tests/api/loadtest.py --url https://test.colibre.fr/api/v1/data --token colibre_xxx
    python tests/api/loadtest.py --token colibre_xxx --levels 1,2,4,8,16,32 --duration 20
    python tests/api/loadtest.py --token colibre_xxx --count-mode both  # mesure le surcoût du COUNT(*)
    python tests/api/loadtest.py --url http://localhost:8050/api/v1/data --duration 5  # local, auth désactivée
"""

import argparse
import asyncio
import random
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

DEFAULT_URL = "https://test.colibre.fr/api/v1/data"

# Mix réaliste de requêtes client. `count_results` n'est PAS fixé ici : il est
# ajouté à l'exécution selon --count-mode (false/true/both), pour mesurer le
# surcoût du COUNT(*). `weight` = fréquence relative dans le mix.
# valeur=None → drapeau nu (sans `=`).
#
# Le scénario d'agrégation ignore count_results côté serveur (pas de `total` en
# mode groupby) : le drapeau lui est donc ajouté mais sans effet, c'est voulu.
SCENARIOS: list[dict] = [
    {
        "name": "sans filtre (page 1)",
        "weight": 3,
        "params": [("page_size", "50")],
    },
    {
        "name": "filtre exact département",
        "weight": 4,
        "params": [
            ("acheteur_departement_code__exact", "44"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "filtre date + tri + colonnes",
        "weight": 3,
        "params": [
            ("dateNotification__greater", "2024-01-01"),
            ("dateNotification__sort", "desc"),
            ("columns", "uid,objet,montant,dateNotification"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "filtre __in (CPV multiples)",
        "weight": 2,
        "params": [
            ("codeCPV__in", "72000000,72200000"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "filtres combinés",
        "weight": 2,
        "params": [
            ("acheteur_departement_code__exact", "75"),
            ("dateNotification__greater", "2023-01-01"),
            ("montant__strictly_greater", "50000"),
            ("dateNotification__sort", "desc"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "page 2",
        "weight": 1,
        "params": [("page", "2"), ("page_size", "50")],
    },
    {
        "name": "agrégation groupby + count",
        "weight": 1,
        "params": [
            ("acheteur_departement_code__groupby", None),
            ("uid__count", None),
            ("page_size", "100"),
        ],
    },
]


def queries_for_mode(mode: str) -> list[tuple[str, int]]:
    """Construit le mix de requêtes pour un mode count_results donné.

    `mode` vaut "false" ou "true" ; il est appended à chaque scénario.
    """
    return [
        (build_query(s["params"] + [("count_results", mode)]), s["weight"])
        for s in SCENARIOS
    ]


def build_query(params: list[tuple[str, str | None]]) -> str:
    """Construit la query string. valeur=None → clé nue (sans `=`)."""
    parts = []
    for key, value in params:
        if value is None:
            parts.append(key)
        else:
            parts.append(f"{key}={quote(str(value), safe=',:')}")
    return "&".join(parts)


def percentile(data: list[float], p: float) -> float:
    if not data:
        return float("nan")
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo)


@dataclass
class LevelResult:
    concurrency: int
    elapsed: float
    latencies: list[float] = field(default_factory=list)  # ms, requêtes 2xx
    errors: int = 0
    statuses: dict[int, int] = field(default_factory=dict)

    @property
    def completed(self) -> int:
        return len(self.latencies) + self.errors

    @property
    def rps(self) -> float:
        return self.completed / self.elapsed if self.elapsed > 0 else 0.0

    @property
    def error_rate(self) -> float:
        return self.errors / self.completed if self.completed else 0.0

    @property
    def median(self) -> float:
        return percentile(self.latencies, 50)

    @property
    def p95(self) -> float:
        return percentile(self.latencies, 95)

    @property
    def maxi(self) -> float:
        return max(self.latencies) if self.latencies else float("nan")


def _pick_query(rng: random.Random, queries: list[tuple[str, int]]) -> str:
    total = sum(w for _, w in queries)
    r = rng.uniform(0, total)
    upto = 0.0
    for q, w in queries:
        upto += w
        if r <= upto:
            return q
    return queries[-1][0]


async def _worker(
    client: httpx.AsyncClient,
    base_url: str,
    queries: list[tuple[str, int]],
    deadline: float,
    result: LevelResult,
    seed: int,
) -> None:
    rng = random.Random(seed)
    while time.perf_counter() < deadline:
        query = _pick_query(rng, queries)
        url = f"{base_url}?{query}"
        t0 = time.perf_counter()
        try:
            resp = await client.get(url)
            dt = (time.perf_counter() - t0) * 1000
            result.statuses[resp.status_code] = (
                result.statuses.get(resp.status_code, 0) + 1
            )
            if 200 <= resp.status_code < 300:
                result.latencies.append(dt)
            else:
                result.errors += 1
        except httpx.RequestError:
            result.statuses[0] = result.statuses.get(0, 0) + 1
            result.errors += 1


async def run_level(
    base_url: str,
    headers: dict,
    queries: list[tuple[str, int]],
    concurrency: int,
    duration: float,
    timeout: float,
) -> LevelResult:
    limits = httpx.Limits(
        max_connections=concurrency + 4,
        max_keepalive_connections=concurrency + 4,
    )
    result = LevelResult(concurrency=concurrency, elapsed=0.0)
    async with httpx.AsyncClient(
        headers=headers, timeout=timeout, limits=limits
    ) as client:
        deadline = time.perf_counter() + duration
        t0 = time.perf_counter()
        tasks = [
            asyncio.create_task(
                _worker(client, base_url, queries, deadline, result, seed=i)
            )
            for i in range(concurrency)
        ]
        await asyncio.gather(*tasks)
        result.elapsed = time.perf_counter() - t0
    return result


async def warmup(
    base_url: str, headers: dict, queries: list[tuple[str, int]], timeout: float
) -> int:
    """Une requête de chauffe ; retourne le statut (pour valider auth/URL)."""
    async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
        query = queries[0][0]
        resp = await client.get(f"{base_url}?{query}")
        return resp.status_code


def _fmt_ms(v: float) -> str:
    return "—" if v != v else f"{v:.0f}"  # v != v → NaN


async def run_sweep(
    args: argparse.Namespace,
    headers: dict,
    queries: list[tuple[str, int]],
    levels: list[int],
    label: str,
) -> LevelResult | None:
    """Balaye les niveaux de concurrence pour un mix donné ; retourne le meilleur.

    `label` identifie le mode dans l'affichage (ex. « count_results=true »).
    """
    header = (
        f"{'conc.':>6}  {'req/s':>8}  {'terminées':>10}  "
        f"{'méd ms':>8}  {'p95 ms':>8}  {'max ms':>8}  {'erreurs':>8}"
    )
    sep = "-" * len(header)
    print(f"\n### {label}\n{sep}\n{header}\n{sep}")

    best: LevelResult | None = None
    for c in levels:
        res = await run_level(
            args.url, headers, queries, c, args.duration, args.timeout
        )
        sustainable = (
            res.error_rate <= args.max_error_rate
            and res.latencies
            and res.p95 <= args.p95_threshold
        )
        flag = "  ✓" if sustainable else "   "
        print(
            f"{res.concurrency:>6}  {res.rps:>8.1f}  {res.completed:>10}  "
            f"{_fmt_ms(res.median):>8}  {_fmt_ms(res.p95):>8}  {_fmt_ms(res.maxi):>8}  "
            f"{res.errors:>4} ({res.error_rate:>4.0%}){flag}"
        )
        if sustainable and (best is None or res.rps > best.rps):
            best = res

        # Arrêt anticipé : serveur clairement saturé (erreurs franches ou p95
        # très au-delà du seuil) → inutile de monter davantage.
        if res.error_rate > 0.10 or (
            res.latencies and res.p95 > 3 * args.p95_threshold
        ):
            print(f"{sep}\n(arrêt anticipé : saturation détectée à concurrence {c})")
            break

    print(sep)
    if best is not None:
        print(
            f"➜ [{label}] débit max soutenable : ~{best.rps:.0f} req/s "
            f"(concurrence {best.concurrency}, p95 {best.p95:.0f} ms, "
            f"erreurs {best.error_rate:.0%})"
        )
        print(
            f"  Marge conseillée pour le client : ~{best.rps * 0.7:.0f} req/s "
            f"(70 % du plateau)."
        )
    else:
        print(
            f"➜ [{label}] aucun niveau n'a tenu le seuil p95 avec des erreurs faibles."
        )
    return best


async def main_async(args: argparse.Namespace) -> int:
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    modes = ["false", "true"] if args.count_mode == "both" else [args.count_mode]

    print(f"\nCible   : {args.url}")
    print(
        f"Niveaux : {levels} | durée/niveau : {args.duration}s | timeout : {args.timeout}s"
    )
    print(f"Modes   : count_results ∈ {modes}")
    print(
        f"Seuil p95 pour « soutenable » : {args.p95_threshold:.0f} ms | erreurs max : {args.max_error_rate:.0%}\n"
    )

    print("Chauffe…", end=" ", flush=True)
    try:
        status = await warmup(
            args.url, headers, queries_for_mode(modes[0]), args.timeout
        )
    except httpx.RequestError as exc:
        print(f"ÉCHEC : {exc}")
        return 1
    print(f"statut {status}")
    if status == 401:
        print("→ 401 : token manquant ou invalide. Fournis --token.", file=sys.stderr)
        return 1
    if not (200 <= status < 300):
        print(f"→ statut inattendu {status}, on continue quand même…", file=sys.stderr)

    bilans: dict[str, LevelResult | None] = {}
    for mode in modes:
        label = f"count_results={mode}"
        bilans[label] = await run_sweep(
            args, headers, queries_for_mode(mode), levels, label
        )

    # Synthèse comparative quand les deux modes ont tourné.
    if len(modes) > 1:
        print("\n=== Synthèse ===")
        for label, best in bilans.items():
            if best is not None:
                print(f"  {label:>22} : ~{best.rps:.0f} req/s (p95 {best.p95:.0f} ms)")
            else:
                print(f"  {label:>22} : non soutenable")
        f, t = bilans.get("count_results=false"), bilans.get("count_results=true")
        if f and t and t.rps > 0:
            print(
                f"\n  → Le COUNT(*) coûte un facteur ~{f.rps / t.rps:.1f}× sur le débit "
                f"soutenable ({f.rps:.0f} → {t.rps:.0f} req/s)."
            )
    print()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test de montée en charge de l'endpoint /data de colibre."
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL, help=f"Endpoint /data (défaut : {DEFAULT_URL})"
    )
    parser.add_argument(
        "--token", default=None, help="Token Bearer colibre (colibre_xxx)"
    )
    parser.add_argument(
        "--levels",
        default="1,2,4,8,16,32,64",
        help="Niveaux de concurrence, séparés par des virgules (défaut : 1,2,4,8,16,32,64)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=15.0,
        help="Durée par niveau, en secondes (défaut : 15)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout par requête, en secondes (défaut : 30)",
    )
    parser.add_argument(
        "--count-mode",
        choices=["false", "true", "both"],
        default="false",
        help=(
            "count_results des requêtes : « false » (sans COUNT(*), défaut), "
            "« true » (avec COUNT(*)), ou « both » (les deux, avec synthèse "
            "du surcoût du COUNT)."
        ),
    )
    parser.add_argument(
        "--p95-threshold",
        type=float,
        default=1000.0,
        help="Seuil de latence p95 (ms) sous lequel un niveau est « soutenable » (défaut : 1000)",
    )
    parser.add_argument(
        "--max-error-rate",
        type=float,
        default=0.01,
        help="Taux d'erreurs max toléré pour « soutenable » (défaut : 0.01)",
    )
    args = parser.parse_args()

    if args.duration <= 0:
        print("--duration doit être > 0", file=sys.stderr)
        sys.exit(1)

    try:
        rc = asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\nInterrompu.", file=sys.stderr)
        rc = 130
    sys.exit(rc)


if __name__ == "__main__":
    main()
