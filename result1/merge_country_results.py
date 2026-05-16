"""
merge_country_results.py
========================
Merges country layer results of 50 countries into Pan-African summary files.
"""

from pathlib import Path

import pandas as pd

RESULTS_DIR = Path("path/to/your/base/directory/web/network_results/country_layer")


def main():
    summary_dfs = []
    isolation_dfs = []
    pairs_dfs = []
    missing = []

    for country_dir in sorted(RESULTS_DIR.iterdir()):
        if not country_dir.is_dir():
            continue
        name = country_dir.name

        summ_csv = country_dir / f"{name}_od_summary.csv"
        iso_csv = country_dir / f"{name}_city_isolation.csv"
        pair_csv = country_dir / f"{name}_od_pairs.csv"

        if not summ_csv.exists():
            missing.append(name)
            continue

        summary_dfs.append(pd.read_csv(summ_csv))
        if iso_csv.exists():
            isolation_dfs.append(pd.read_csv(iso_csv))
        if pair_csv.exists():
            pairs_dfs.append(pd.read_csv(pair_csv))

    if missing:
        print(f"[WARN] Missing results for countries, skipping: {missing}")

    if not summary_dfs:
        print("No data to merge")
        return

    summary = pd.concat(summary_dfs, ignore_index=True)
    out_summ = RESULTS_DIR / "africa_country_summary.csv"
    summary.to_csv(out_summ, index=False)
    print(f"Country-level summary: {len(summary)} countries -> {out_summ}")

    if isolation_dfs:
        iso_all = pd.concat(isolation_dfs, ignore_index=True)
        iso_all = iso_all.sort_values(
            ["disconnection_ratio", "mean_travel_increase_pct"],
            ascending=[False, False],
        ).reset_index(drop=True)
        out_iso = RESULTS_DIR / "africa_city_isolation.csv"
        iso_all.to_csv(out_iso, index=False)
        print(f"City isolation risks: {len(iso_all)} cities -> {out_iso}")

    if pairs_dfs:
        pairs_all = pd.concat(pairs_dfs, ignore_index=True)
        out_pairs = RESULTS_DIR / "africa_od_pairs.csv"
        pairs_all.to_csv(out_pairs, index=False)
        print(f"Complete city pairs: {len(pairs_all)} pairs -> {out_pairs}")

    print(f"\n{'=' * 60}")
    print(f"  Pan-African country layer summary ({len(summary)} countries)")
    print(f"{'=' * 60}")

    n_cities_total = summary["n_cities"].sum()
    n_pairs_total = summary["n_city_pairs"].sum()
    n_disc_total = summary["n_climate_disconnected"].sum()
    disc_ratio = n_disc_total / n_pairs_total if n_pairs_total > 0 else float("nan")

    print(f"  Total cities:                     {n_cities_total}")
    print(f"  Total city pairs:                 {n_pairs_total}")
    print(
        f"  Climate disconnected pairs:       {n_disc_total} ({disc_ratio * 100:.1f}%)"
    )
    print(
        f"  Travel time increase (Mean):      {summary['mean_travel_increase_pct'].mean():.2f}%"
    )
    print(
        f"  Travel time increase (Median):    {summary['median_travel_increase_pct'].median():.2f}%"
    )
    print(
        f"  Severely degraded (>50%) pairs:   {summary['n_severe_increase'].sum()} "
        f"({summary['pct_severe_increase'].mean():.1f}% avg)"
    )

    print(f"\n  Top 10 countries with highest travel time increase:")
    top10 = summary.nlargest(10, "mean_travel_increase_pct")[
        [
            "country",
            "n_cities",
            "n_city_pairs",
            "n_climate_disconnected",
            "mean_travel_increase_pct",
            "pct_severe_increase",
        ]
    ]
    print(top10.to_string(index=False))

    if isolation_dfs:
        print(f"\n  Top 10 cities with highest isolation risks:")
        top_cities = iso_all.head(10)[
            [
                "country",
                "city_name",
                "level",
                "n_climate_disconnected",
                "disconnection_ratio",
                "mean_travel_increase_pct",
            ]
        ]
        print(top_cities.to_string(index=False))


if __name__ == "__main__":
    main()
