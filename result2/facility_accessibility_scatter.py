"""
facility_accessibility_scatter.py
==================================
Sub-argument 2 — Direction 3: Healthcare Facility Density × Accessibility

Argument
--------
Countries with sparser healthcare infrastructure (fewer facilities per capita)
have longer baseline travel times AND suffer larger climate-induced increases —
the three dimensions converge on the same set of structurally disadvantaged
countries.

Analysis
--------
1. Main scatter: facility density (x) vs PWMTT baseline (y),
   colour = pwmtt_delta, size = population.
   → Countries in the bottom-left corner (sparse facilities + long travel time)
     also tend to be dark-coloured (large climate impact).

2. Secondary scatter: facility density vs pwmtt_delta directly,
   with a Spearman ρ annotation.
   → Direct test: does lower density → greater climate impact?

3. Quadrant summary table: divide countries into four quadrants by median
   facility density and median PWMTT. Report mean pwmtt_delta per quadrant.
   → "Sparse + far" quadrant should have the highest climate impact.

Population denominator
----------------------
Uses World Bank total population (`population` column from worldbank_indicators.csv)
for the facility density calculation, NOT the road-network-captured population
from the health accessibility summary (which only reflects unpaved-road coverage).
Falls back to the network-captured population if WB data unavailable.

Inputs
------
  <BASE_DIR>/RAW/worldbank_indicators.csv          (precomputed indicator table)
  <BASE_DIR>/web/health_accessibility/
    country_accessibility_summary.csv

Outputs → <BASE_DIR>/web/network_results/facility_accessibility/
  facility_density_scatter.png      main 1×2 scatter figure
  quadrant_summary.csv              four-quadrant statistics

Usage
-----
  python result2/facility_accessibility_scatter.py --base <BASE_DIR>
"""

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

_DEFAULT_BASE = Path("path/to/base")

LABEL_COUNTRIES = {
    "Somalia",
    "Mauritania",
    "Sudan",
    "CongoDR",
    "Nigeria",
    "SouthAfrica",
    "Morocco",
    "Kenya",
    "Ethiopia",
    "Niger",
    "Chad",
    "Mali",
    "Botswana",
    "Gabon",
}


def load_data(base: Path) -> pd.DataFrame:
    acc_path = (
        base / "web" / "health_accessibility" / "country_accessibility_summary.csv"
    )
    wb_path = base / "RAW" / "worldbank_indicators.csv"

    acc = pd.read_csv(acc_path)

    if wb_path.exists():
        wb = pd.read_csv(wb_path)[["country", "population"]].rename(
            columns={"population": "wb_population"}
        )
        df = acc.merge(wb, on="country", how="left")
    else:
        print(
            "  [WARN] worldbank_indicators.csv not found — "
            "using network-captured population as denominator."
        )
        df = acc.copy()
        df["wb_population"] = df["total_population"]

    df["pop_denom"] = df["wb_population"].combine_first(df["total_population"])
    df["pop_denom"] = df["pop_denom"].replace(0, np.nan)

    df["facility_per_million"] = df["n_health_facilities"] / df["pop_denom"] * 1e6

    df = df.dropna(subset=["facility_per_million", "pwmtt_normal", "pwmtt_delta"])
    print(f"  Countries with complete data: {len(df)}")
    return df


def plot_main_scatter(df: pd.DataFrame, out_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]
    delta = df["pwmtt_delta"].values
    norm = mcolors.Normalize(vmin=0, vmax=np.percentile(delta[np.isfinite(delta)], 95))
    cmap = cm.get_cmap("YlOrRd")
    colors = cmap(norm(delta))

    pop = df["pop_denom"].values
    pop_norm = np.sqrt(pop / np.nanmax(pop))
    sizes = 40 + pop_norm * 600

    sc = ax.scatter(
        df["facility_per_million"],
        df["pwmtt_normal"],
        s=sizes,
        c=colors,
        alpha=0.8,
        edgecolors="white",
        lw=0.6,
    )

    for _, row in df.iterrows():
        if row["country"] in LABEL_COUNTRIES:
            ax.annotate(
                row["country"],
                (row["facility_per_million"], row["pwmtt_normal"]),
                fontsize=7.5,
                ha="left",
                xytext=(4, 2),
                textcoords="offset points",
                color="#333333",
            )

    med_dens = df["facility_per_million"].median()
    med_pwmtt = df["pwmtt_normal"].median()
    ax.axvline(med_dens, color="gray", lw=0.8, ls="--", alpha=0.6)
    ax.axhline(med_pwmtt, color="gray", lw=0.8, ls="--", alpha=0.6)

    ax.set_xlabel("Health facilities per million people", fontsize=11)
    ax.set_ylabel("Baseline PWMTT — normal weather (hours)", fontsize=11)
    ax.set_title(
        "Facility density vs baseline accessibility\n"
        "Colour = climate impact  |  Size = population",
        fontsize=11,
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label("Climate-induced PWMTT Δ (hours)", fontsize=9)

    rho, pval = spearmanr(df["facility_per_million"], df["pwmtt_normal"])
    sig = (
        "***"
        if pval < 0.001
        else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
    )
    ax.text(
        0.97,
        0.97,
        f"ρ = {rho:+.3f} {sig}\np = {pval:.3f}",
        transform=ax.transAxes,
        fontsize=9,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.85),
    )
    ax.grid(alpha=0.25)

    ax2 = axes[1]
    rho2, pval2 = spearmanr(df["facility_per_million"], df["pwmtt_delta"])
    sig2 = (
        "***"
        if pval2 < 0.001
        else ("**" if pval2 < 0.01 else ("*" if pval2 < 0.05 else "ns"))
    )

    ax2.scatter(
        df["facility_per_million"],
        df["pwmtt_delta"],
        s=sizes,
        c="#2166ac",
        alpha=0.75,
        edgecolors="white",
        lw=0.6,
    )

    for _, row in df.iterrows():
        if row["country"] in LABEL_COUNTRIES:
            ax2.annotate(
                row["country"],
                (row["facility_per_million"], row["pwmtt_delta"]),
                fontsize=7.5,
                ha="left",
                xytext=(4, 2),
                textcoords="offset points",
                color="#333333",
            )

    valid = df[["facility_per_million", "pwmtt_delta"]].dropna()
    if len(valid) >= 5:
        z = np.polyfit(valid["facility_per_million"], valid["pwmtt_delta"], 1)
        x_line = np.linspace(
            valid["facility_per_million"].min(),
            valid["facility_per_million"].max(),
            100,
        )
        ax2.plot(x_line, np.poly1d(z)(x_line), "r--", lw=1.5, alpha=0.7)

    ax2.set_xlabel("Health facilities per million people", fontsize=11)
    ax2.set_ylabel("Climate-induced PWMTT increase (hours)", fontsize=11)
    ax2.set_title(
        "Facility density vs climate impact (direct)\n" "Size = population", fontsize=11
    )
    ax2.text(
        0.97,
        0.97,
        f"ρ = {rho2:+.3f} {sig2}\np = {pval2:.3f}",
        transform=ax2.transAxes,
        fontsize=9,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.85),
    )
    ax2.grid(alpha=0.25)

    plt.tight_layout()
    out_path = out_dir / "facility_density_scatter.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → facility_density_scatter.png")


def compute_quadrant_summary(df: pd.DataFrame, out_dir: Path):
    """
    Four quadrants split by median facility density and median PWMTT.
    Reports mean / median pwmtt_delta and country count per quadrant.
    """
    med_dens = df["facility_per_million"].median()
    med_pwmtt = df["pwmtt_normal"].median()

    df["q_dens"] = df["facility_per_million"].apply(
        lambda x: "Dense" if x >= med_dens else "Sparse"
    )
    df["q_pwmtt"] = df["pwmtt_normal"].apply(
        lambda x: "Far" if x >= med_pwmtt else "Near"
    )
    df["quadrant"] = df["q_dens"] + " facilities / " + df["q_pwmtt"] + " facilities"

    labels = {
        ("Dense", "Near"): "Dense facilities / Short travel  (best-off)",
        ("Dense", "Far"): "Dense facilities / Long travel   (infra-rich, remote)",
        ("Sparse", "Near"): "Sparse facilities / Short travel (urban-concentrated)",
        ("Sparse", "Far"): "Sparse facilities / Long travel  ★ WORST-OFF",
    }

    rows = []
    for (dens, pwmtt), label in labels.items():
        mask = (df["q_dens"] == dens) & (df["q_pwmtt"] == pwmtt)
        sub = df[mask]
        rows.append(
            {
                "quadrant": label,
                "n_countries": len(sub),
                "countries": ", ".join(sorted(sub["country"].tolist())),
                "mean_pwmtt_delta": round(sub["pwmtt_delta"].mean(), 4),
                "median_pwmtt_delta": round(sub["pwmtt_delta"].median(), 4),
                "mean_pwmtt_normal": round(sub["pwmtt_normal"].mean(), 4),
            }
        )

    df_q = pd.DataFrame(rows)
    df_q.to_csv(out_dir / "quadrant_summary.csv", index=False)

    print("\n  Quadrant summary:")
    for _, row in df_q.iterrows():
        print(f"    {row['quadrant']}")
        print(
            f"      n={row['n_countries']}  "
            f"mean Δ={row['mean_pwmtt_delta']:.3f}h  "
            f"median Δ={row['median_pwmtt_delta']:.3f}h"
        )
        print(f"      Countries: {row['countries'][:80]}...")
    print(f"\n  Saved → quadrant_summary.csv")

    return df_q


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web" / "network_results" / "facility_accessibility"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Facility Density × Accessibility Analysis (Direction 3)")
    print(f"{'='*60}")

    df = load_data(base)

    print(f"\n{'='*60}")
    print("  Step 1 — Scatter Plots")
    print(f"{'='*60}")
    plot_main_scatter(df, out_dir)

    print(f"\n{'='*60}")
    print("  Step 2 — Quadrant Summary")
    print(f"{'='*60}")
    compute_quadrant_summary(df, out_dir)

    print(f"\n  All outputs in: {out_dir}")


if __name__ == "__main__":
    main()
