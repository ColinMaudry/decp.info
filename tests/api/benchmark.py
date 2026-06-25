#!/usr/bin/env python
"""Benchmark comparatif de l'endpoint /data : decp.info vs data.gouv.fr.

Les deux APIs partagent le même schéma de requête (mêmes opérateurs), donc
chaque scénario est envoyé à l'identique aux deux et les temps de réponse
sont comparés côte à côte.

Usage :
    python tests/api/benchmark.py --token decpinfo_xxx
    python tests/api/benchmark.py --url http://localhost:8050/api/v1/data --token decpinfo_xxx
    python tests/api/benchmark.py --decp-only --token decpinfo_xxx --runs 20

Par défaut, --url pointe vers la production decp.info ; data.gouv.fr est
interrogé sans authentification.

"""

import argparse
import sys
import time
from dataclasses import dataclass, field
from urllib.parse import quote

import httpx

DECP_DEFAULT_URL = "https://decp.info/api/v1/data"
DATAGOUV_DEFAULT_URL = (
    "https://tabular-api.data.gouv.fr/api/resources/"
    "22847056-61df-452d-837d-8b8ceadbfc52/data/"
)

# Chaque scénario : liste de (clé, valeur). valeur=None → drapeau nu (sans `=`),
# requis par data.gouv.fr pour les opérateurs d'agrégation et isnull.
SCENARIOS: list[dict] = [
    {
        "name": "sans filtre (page 1, 50 résultats)",
        "params": [("page", "1"), ("page_size", "50")],
    },
    {
        "name": "filtre __exact sur département",
        "params": [("acheteur_departement_code__exact", "44"), ("page_size", "50")],
    },
    {
        "name": "filtre __differs sur département",
        "params": [("acheteur_departement_code__differs", "44"), ("page_size", "50")],
    },
    {
        "name": "filtre __contains sur objet",
        "params": [("objet__contains", "informatique"), ("page_size", "50")],
    },
    {
        "name": "filtre __greater sur date",
        "params": [("dateNotification__greater", "2024-01-01"), ("page_size", "50")],
    },
    {
        "name": "filtre __strictly_greater sur montant",
        "params": [("montant__strictly_greater", "100000"), ("page_size", "50")],
    },
    {
        "name": "filtre __in (CPV multiples)",
        "params": [("codeCPV__in", "72000000,72200000"), ("page_size", "50")],
    },
    {
        "name": "filtre __isnull sur montant",
        "params": [("montant__isnull", None), ("page_size", "50")],
    },
    {
        "name": "tri desc + colonnes sélectionnées",
        "params": [
            ("dateNotification__sort", "desc"),
            ("columns", "uid,objet,montant,dateNotification"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "filtres combinés",
        "params": [
            ("acheteur_departement_code__exact", "75"),
            ("dateNotification__greater", "2023-01-01"),
            ("montant__strictly_greater", "50000"),
            ("dateNotification__sort", "desc"),
            ("page_size", "50"),
        ],
    },
    {
        "name": "agrégation groupby + count",
        "params": [
            ("acheteur_departement_code__groupby", None),
            ("uid__count", None),
            ("page_size", "100"),
        ],
    },
    {
        "name": "agrégation groupby + sum + avg",
        "params": [
            ("acheteur_departement_code__groupby", None),
            ("montant__sum", None),
            ("montant__avg", None),
            ("page_size", "100"),
        ],
    },
    {
        "name": "page 2",
        "params": [("page", "2"), ("page_size", "50")],
    },
    {
        "name": "count_results=false (optim COUNT(*))",
        "params": [("page_size", "50"), ("count_results", "false")],
        "decp_only": True,
    },
]

COL_NAME = 40
COL_STAT = 9


@dataclass
class Target:
    label: str
    base_url: str
    headers: dict = field(default_factory=dict)


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


def measure(target: Target, query: str, runs: int) -> dict | None:
    """Chauffe (1 requête non mesurée) puis chronomètre `runs` requêtes."""
    url = f"{target.base_url}?{query}"
    try:
        warm = httpx.get(url, headers=target.headers, timeout=30)
        last_status = warm.status_code
    except httpx.RequestError as exc:
        return {"error": str(exc), "status": 0}

    timings: list[float] = []
    for _ in range(runs):
        try:
            t0 = time.perf_counter()
            resp = httpx.get(url, headers=target.headers, timeout=30)
            timings.append((time.perf_counter() - t0) * 1000)
            last_status = resp.status_code
        except httpx.RequestError as exc:
            return {"error": str(exc), "status": 0}

    return {
        "status": last_status,
        "median": percentile(timings, 50),
        "p95": percentile(timings, 95),
        "min": min(timings),
        "max": max(timings),
    }


def run_benchmark(targets: list[Target], decp_label: str, runs: int) -> None:
    print("\nAVERTISSEMENT : volumes de données différents entre les deux APIs.")
    print(f"Scénarios : {len(SCENARIOS)} | Répétitions : {runs}\n")

    rows: list[dict] = []
    for scenario in SCENARIOS:
        query = build_query(scenario["params"])
        decp_only = scenario.get("decp_only", False)
        active = [t for t in targets if not (decp_only and t.label != decp_label)]

        measures = {t.label: measure(t, query, runs) for t in active}
        rows.append({"name": scenario["name"], "measures": measures})

        bits = []
        for t in active:
            m = measures[t.label]
            if "error" in m:
                bits.append(f"{t.label}: ERREUR")
            else:
                bits.append(f"{t.label}: méd {m['median']:.0f}ms [{m['status']}]")
        print(f"  {scenario['name'][:COL_NAME]:<{COL_NAME}}  " + " | ".join(bits))

    _print_summary(rows, targets, decp_label)


def _fmt(m: dict | None, key: str) -> str:
    if m is None:
        return "—"
    if "error" in m:
        return "ERR"
    return f"{m[key]:.0f}"


def _print_summary(rows: list[dict], targets: list[Target], decp_label: str) -> None:
    dg = next((t.label for t in targets if t.label != decp_label), None)

    header = (
        f"{'Scénario':<{COL_NAME}}"
        f"  {'DG méd':>{COL_STAT}}  {'DG p95':>{COL_STAT}}"
        f"  {'decp méd':>{COL_STAT}}  {'decp p95':>{COL_STAT}}"
        f"  {'ratio':>7}"
    )
    sep = "-" * len(header)
    print(
        f"\n{'=' * len(header)}\nRÉSUMÉ (ratio = decp / data.gouv.fr, <1 = decp plus rapide)"
    )
    print(f"{'=' * len(header)}\n{header}\n{sep}")

    for row in rows:
        m_decp = row["measures"].get(decp_label)
        m_dg = row["measures"].get(dg) if dg else None

        ratio = "—"
        if m_decp and m_dg and "error" not in m_decp and "error" not in m_dg:
            if m_dg["median"] > 0:
                ratio = f"{m_decp['median'] / m_dg['median']:.2f}"

        print(
            f"{row['name'][:COL_NAME]:<{COL_NAME}}"
            f"  {_fmt(m_dg, 'median'):>{COL_STAT}}  {_fmt(m_dg, 'p95'):>{COL_STAT}}"
            f"  {_fmt(m_decp, 'median'):>{COL_STAT}}  {_fmt(m_decp, 'p95'):>{COL_STAT}}"
            f"  {ratio:>7}"
        )
    print(sep)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark comparatif decp.info vs data.gouv.fr (/data)"
    )
    parser.add_argument(
        "--url",
        default=DECP_DEFAULT_URL,
        help=f"Endpoint /data de decp.info (défaut : {DECP_DEFAULT_URL})",
    )
    parser.add_argument(
        "--datagouv-url",
        default=DATAGOUV_DEFAULT_URL,
        help="Endpoint /data/ de la ressource data.gouv.fr",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Token Bearer decp.info (format decpinfo_xxx)",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Répétitions chronométrées par scénario (défaut : 5)",
    )
    parser.add_argument(
        "--decp-only",
        action="store_true",
        help="Ne benchmarker que decp.info (saute data.gouv.fr)",
    )
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs doit être ≥ 1", file=sys.stderr)
        sys.exit(1)

    decp_label = "decp.info"
    decp_headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    decp = Target(label=decp_label, base_url=args.url, headers=decp_headers)

    targets = [decp]
    if not args.decp_only:
        # data.gouv.fr d'abord pour l'affichage côte à côte
        targets.insert(0, Target(label="data.gouv.fr", base_url=args.datagouv_url))

    run_benchmark(targets, decp_label, args.runs)


if __name__ == "__main__":
    main()
