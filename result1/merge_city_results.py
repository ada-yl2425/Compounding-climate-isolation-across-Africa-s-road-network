"""
merge_city_results.py
=====================
Merges city layer results of 50 countries into a Pan-African summary file.
"""

from pathlib import Path

import pandas as pd

RESULTS_DIR = Path("path/to/your/base/directory/web/network_results/city_layer")


def main():
    all_dfs = []
    missing = []

    for country_dir in sorted(RESULTS_DIR.iterdir()):
        if not country_dir.is_dir():
            continue
        csv = country_dir / f"{country_dir.name}_district_summary.csv"
        if not csv.exists():
            missing.append(country_dir.name)
            continue
        df = pd.read_csv(csv)
        all_dfs.append(df)

    if missing:
        print(f"[WARN] Missing results for countries, skipping: {missing}")

    if not all_dfs:
        print("No data to merge")
        return

    merged = pd.concat(all_dfs, ignore_index=True)
    out_path = RESULTS_DIR / "africa_city_summary.csv"
    merged.to_csv(out_path, index=False)
    print(f"Merged: {len(merged):,} districts, {merged['country'].nunique()} countries")
    print(f"Saved: {out_path}")

    def q25(x):
        return x.quantile(0.25)

    def q75(x):
        return x.quantile(0.75)

    agg = (
        merged.groupby("country")
        .agg(
            n_districts=("district_id", "count"),
            nodes_median=("n_nodes", "median"),
            edges_median=("n_edges", "median"),
            lcc_ratio_mean=("lcc_ratio", "mean"),
            bridge_ratio_mean=("bridge_ratio", "mean"),
            L1_count_total=("L1_count", "sum"),
            road_deg_mean=("mean_road_degradation_pct", "mean"),
            road_deg_std=("mean_road_degradation_pct", "std"),
            p_block_mean=("mean_p_block", "mean"),
            E_normal_mean=("E_normal", "mean"),
            E_extreme_mean=("E_extreme", "mean"),
            dE_pct_mean=("dE_pct", "mean"),
            dE_pct_std=("dE_pct", "std"),
            dE_pct_q75=("dE_pct", q75),
            D_normal_mean=("D_normal", "mean"),
            D_extreme_mean=("D_extreme", "mean"),
            delta_comp_mean=("delta_components", "mean"),
            delta_comp_max=("delta_components", "max"),
            amp_mean=("amplification_ratio", "mean"),
            amp_median=("amplification_ratio", "median"),
            amp_q75=("amplification_ratio", q75),
            amp_gt1_pct=("amplification_ratio", lambda x: (x > 1).mean() * 100),
            qc_mean=("q_c", "mean"),
            qc_median=("q_c", "median"),
            perc_E_drop_mean=("perc_E_drop_at_qc", "mean"),
        )
        .reset_index()
    )

    stats_path = RESULTS_DIR / "africa_city_summary_stats.csv"
    agg.to_csv(stats_path, index=False)
    print(f"\nCountry-level stats: {stats_path}")

    print(f"\n{'=' * 60}")
    print(f"  Pan-African city layer summary ({len(merged):,} districts)")
    print(f"{'=' * 60}")
    print(
        f"  Avg road degradation:          {merged['mean_road_degradation_pct'].mean():.2f}%"
    )
    print(f"  Avg efficiency loss (ΔE):      {merged['dE_pct'].mean():.2f}%")
    print(
        f"  Avg amplification factor:      {merged['amplification_ratio'].mean():.3f}"
    )
    print(
        f"  Districts with amp > 1:        {(merged['amplification_ratio'] > 1).mean() * 100:.1f}%"
    )
    print(f"  Avg percolation threshold q_c: {merged['q_c'].mean():.3f}")
    print(f"  Avg bridge ratio:              {merged['bridge_ratio'].mean():.3f}")

    print(f"\n  Top 10 districts by amplification factor:")
    top10 = merged.nlargest(10, "amplification_ratio")[
        [
            "country",
            "district_id",
            "n_nodes",
            "mean_road_degradation_pct",
            "dE_pct",
            "amplification_ratio",
            "bridge_ratio",
            "q_c",
        ]
    ]
    print(top10.to_string(index=False))

    print(f"\n  Top 10 countries by mean amplification:")
    top_countries = agg.nlargest(10, "amp_mean")[
        [
            "country",
            "n_districts",
            "road_deg_mean",
            "dE_pct_mean",
            "amp_mean",
            "qc_mean",
        ]
    ]
    print(top_countries.to_string(index=False))


if __name__ == "__main__":
    main()
