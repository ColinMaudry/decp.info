#!/usr/bin/env python
"""Benchmark de l'endpoint /data de l'API privée decp.info.

Usage :
    python tests/benchmark_api.py --url http://localhost:8050/api/v1/data --token decpinfo_xxx
    python tests/benchmark_api.py --url https://decp.info/api/v1/data --token decpinfo_xxx --runs 20

Le script mesure le temps de réponse de chaque scénario et affiche un tableau
de statistiques (min / médiane / p95 / max).
"""

import argparse
import statistics
import sys
import time

import httpx

SCENARIOS: list[dict] = [
    {
        "name": "sans filtre (page 1, 50 résultats)",
        "params": {"page": 1, "page_size": 50},
    },
    {
        "name": "filtre __exact sur département",
        "params": {"acheteur_departement_code__exact": "44", "page_size": 50},
    },
    {
        "name": "filtre __contains sur objet",
        "params": {"objet__contains": "informatique", "page_size": 50},
    },
    {
        "name": "filtre __greater sur date",
        "params": {"dateNotification__greater": "2024-01-01", "page_size": 50},
    },
    {
        "name": "filtre __strictly_greater sur montant",
        "params": {"montant__strictly_greater": "100000", "page_size": 50},
    },
    {
        "name": "filtre __in (CPV multiples)",
        "params": {"cpv_8__in": "72000000,72200000", "page_size": 50},
    },
    {
        "name": "filtre __isnull",
        "params": {"montant__isnull": "", "page_size": 50},
    },
    {
        "name": "tri desc + colonnes sélectionnées",
        "params": {
            "dateNotification__sort": "desc",
            "columns": "uid,objet,montant,dateNotification",
            "page_size": 50,
        },
    },
    {
        "name": "filtres combinés",
        "params": {
            "acheteur_departement_code__exact": "75",
            "dateNotification__greater": "2023-01-01",
            "montant__strictly_greater": "50000",
            "dateNotification__sort": "desc",
            "page_size": 50,
        },
    },
    {
        "name": "count=false (économise COUNT(*))",
        "params": {"page_size": 50, "count": "false"},
    },
    {
        "name": "page 2",
        "params": {"page": 2, "page_size": 50},
    },
]

COL_NAME = 44
COL_STATUS = 8
COL_STAT = 10


def percentile(data: list[float], p: float) -> float:
    if not data:
        return float("nan")
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (k - lo)


def run_benchmark(base_url: str, token: str | None, runs: int) -> None:
    auth_header = {"Authorization": f"Bearer {token}"} if token else {}
    results: list[dict] = []

    print(f"\nBenchmark {base_url}")
    print(f"Scénarios : {len(SCENARIOS)} | Répétitions : {runs}\n")

    for scenario in SCENARIOS:
        timings: list[float] = []
        last_status = 0

        for _ in range(runs):
            headers = auth_header
            url = base_url
            params = scenario["params"]

            try:
                t0 = time.perf_counter()
                resp = httpx.get(url, params=params, headers=headers, timeout=30)
                elapsed = (time.perf_counter() - t0) * 1000
                last_status = resp.status_code
                timings.append(elapsed)
            except httpx.RequestError as exc:
                print(f"  ERREUR réseau : {exc}")
                last_status = 0
                break

        if timings:
            results.append(
                {
                    "name": scenario["name"],
                    "status": last_status,
                    "min": min(timings),
                    "median": percentile(timings, 50),
                    "p95": percentile(timings, 95),
                    "max": max(timings),
                    "mean": statistics.mean(timings),
                    "runs": len(timings),
                }
            )
            status_str = f"[{last_status}]"
            print(
                f"  {scenario['name'][:COL_NAME]:<{COL_NAME}}"
                f"  {status_str:<{COL_STATUS}}"
                f"  médiane {results[-1]['median']:>7.1f} ms"
                f"  p95 {results[-1]['p95']:>7.1f} ms"
            )
        else:
            print(f"  {scenario['name'][:COL_NAME]:<{COL_NAME}}  ÉCHEC")

    _print_summary(results)


def _print_summary(results: list[dict]) -> None:
    if not results:
        return

    sep = "-" * (COL_NAME + COL_STATUS + 4 * (COL_STAT + 3) + 6)
    header = (
        f"\n{'Scénario':<{COL_NAME}}  {'Status':<{COL_STATUS}}"
        f"  {'Min (ms)':>{COL_STAT}}"
        f"  {'Médiane (ms)':>{COL_STAT}}"
        f"  {'P95 (ms)':>{COL_STAT}}"
        f"  {'Max (ms)':>{COL_STAT}}"
    )
    print(f"\n{'=' * len(sep)}")
    print("RÉSUMÉ")
    print(f"{'=' * len(sep)}")
    print(header)
    print(sep)

    for r in results:
        status_str = f"[{r['status']}]"
        print(
            f"{r['name'][:COL_NAME]:<{COL_NAME}}"
            f"  {status_str:<{COL_STATUS}}"
            f"  {r['min']:>{COL_STAT}.1f}"
            f"  {r['median']:>{COL_STAT}.1f}"
            f"  {r['p95']:>{COL_STAT}.1f}"
            f"  {r['max']:>{COL_STAT}.1f}"
        )

    print(sep)
    medians = [r["median"] for r in results]
    print(
        f"\nMédiane globale : {statistics.mean(medians):.1f} ms"
        f" | Pire p95 : {max(r['p95'] for r in results):.1f} ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark de l'API privée decp.info")
    parser.add_argument(
        "--url",
        default="http://localhost:8050/api/v1/data",
        help="URL complète de l'endpoint /data (défaut : http://localhost:8050/api/v1/data)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Token Bearer API (format : decpinfo_xxxxx) — omis si l'API n'exige pas d'auth",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=5,
        help="Nombre de répétitions par scénario (défaut : 5)",
    )
    args = parser.parse_args()

    if args.runs < 1:
        print("--runs doit être ≥ 1", file=sys.stderr)
        sys.exit(1)

    run_benchmark(args.url, args.token, args.runs)


if __name__ == "__main__":
    main()
