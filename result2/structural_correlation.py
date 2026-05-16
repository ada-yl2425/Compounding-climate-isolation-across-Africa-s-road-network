"""
structural_correlation.py
=========================
Sub-argument 2 — Direction 1: Cross-national Structural Correlation

Argument
--------
Countries that are structurally disadvantaged (low GDP, sparse health
infrastructure, poor roads) also face greater climate-driven accessibility
loss — proving that climate change amplifies pre-existing inequality at the
country level.

Analysis
--------
1. Spearman correlation matrix: 4 World Bank structural indicators × 2
   accessibility metrics (pwmtt_normal, pwmtt_delta).
2. 2×4 scatter panel: each WB indicator vs pwmtt_normal (left) and
   pwmtt_delta (right), with country labels for outliers.
3. Bubble chart: GDP per capita vs PWMTT, bubble size = population,
   colour = pwmtt_delta — one figure that conveys the full argument.

Inputs
------
  BASE_DIR/RAW/worldbank_indicators.csv          (from fetch_worldbank_indicators.py)
  BASE_DIR/web/health_accessibility/
    country_accessibility_summary.csv

Outputs → BASE_DIR/web/network_results/structural_correlation/
  structural_correlation_matrix.csv    Spearman ρ and p-values (8 pairs)
  structural_scatter_panel.png         2×4 scatter subplots
  bubble_gdp_pwmtt.png                 GDP × PWMTT × delta bubble chart

Usage
-----
  python web/structural_correlation.py
  python web/structural_correlation.py --base /path/to/africa_pavement
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

_DEFAULT_BASE = Path("path/to")

# World Bank indicators to test (column name → display label)
WB_INDICATORS = {
    "gdp_per_capita": "GDP per capita (USD)",
    "hospital_beds_per_1000": "Hospital beds per 1,000 people",
    "paved_road_pct": "Paved roads (% of total)",
    "health_exp_per_capita": "Health expenditure per capita (USD)",
}

# Accessibility metrics (column name → display label)
ACCESS_METRICS = {
    "pwmtt_normal": "Baseline PWMTT (hours)\n[normal weather]",
    "pwmtt_delta": "Climate-induced PWMTT increase (hours)\n[extreme − normal]",
}

# Countries to label on scatter plots (outliers / notable cases)
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
}


# =============================================================================
# LOAD & MERGE
# =============================================================================
def load_data(base: Path) -> pd.DataFrame:
    wb_path = base / "RAW" / "worldbank_indicators.csv"
    acc_path = (
        base / "web" / "health_accessibility" / "country_accessibility_summary.csv"
    )

    if not wb_path.exists():
        raise FileNotFoundError(
            f"{wb_path} not found.\n"
            "Run: python data_procession/fetch_worldbank_indicators.py"
        )

    wb = pd.read_csv(wb_path)
    acc = pd.read_csv(acc_path)

    df = acc.merge(wb, on="country", how="inner")
    print(f"  Merged rows: {len(df)}  (acc={len(acc)}, wb={len(wb)})")

    # Drop rows where both key metrics are null
    df = df.dropna(subset=["pwmtt_normal", "pwmtt_delta"])
    print(f"  After dropping null accessibility: {len(df)}")
    return df


# =============================================================================
# STEP 1 — SPEARMAN CORRELATION MATRIX
# =============================================================================
def compute_correlations(df: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    print("\n  Spearman correlations:")
    records = []
    for wb_col, wb_label in WB_INDICATORS.items():
        for acc_col, acc_label in ACCESS_METRICS.items():
            sub = df[[wb_col, acc_col]].dropna()
            if len(sub) < 5:
                print(f"    {wb_col} × {acc_col}: insufficient data (n={len(sub)})")
                records.append(
                    dict(
                        wb_indicator=wb_col,
                        wb_label=wb_label,
                        access_metric=acc_col,
                        n=len(sub),
                        spearman_rho=np.nan,
                        p_value=np.nan,
                    )
                )
                continue
            rho, pval = spearmanr(sub[wb_col], sub[acc_col])
            sig = (
                "***"
                if pval < 0.001
                else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
            )
            print(
                f"    {wb_col:<30} × {acc_col:<15}  "
                f"ρ={rho:+.3f}  p={pval:.3f} {sig}  (n={len(sub)})"
            )
            records.append(
                dict(
                    wb_indicator=wb_col,
                    wb_label=wb_label,
                    access_metric=acc_col,
                    n=len(sub),
                    spearman_rho=round(rho, 4),
                    p_value=round(pval, 4),
                    significance=sig,
                )
            )

    df_corr = pd.DataFrame(records)
    df_corr.to_csv(out_dir / "structural_correlation_matrix.csv", index=False)
    print(f"\n  Saved → structural_correlation_matrix.csv")
    return df_corr


# =============================================================================
# STEP 2 — SCATTER PANEL (4 WB indicators × 2 accessibility metrics)
# =============================================================================
def plot_scatter_panel(df: pd.DataFrame, df_corr: pd.DataFrame, out_dir: Path):
    n_wb = len(WB_INDICATORS)
    n_acc = len(ACCESS_METRICS)
    fig, axes = plt.subplots(n_wb, n_acc, figsize=(5 * n_acc, 4.5 * n_wb))

    for r, (wb_col, wb_label) in enumerate(WB_INDICATORS.items()):
        for c, (acc_col, acc_label) in enumerate(ACCESS_METRICS.items()):
            ax = axes[r, c]
            sub = df[[wb_col, acc_col, "country"]].dropna()

            if len(sub) < 3:
                ax.text(
                    0.5,
                    0.5,
                    "Insufficient data",
                    ha="center",
                    va="center",
                    transform=ax.transAxes,
                )
                continue

            ax.scatter(
                sub[wb_col],
                sub[acc_col],
                s=40,
                alpha=0.7,
                color="#2166ac",
                edgecolors="white",
                lw=0.5,
            )

            # Label outliers
            for _, row in sub.iterrows():
                if row["country"] in LABEL_COUNTRIES:
                    ax.annotate(
                        row["country"],
                        (row[wb_col], row[acc_col]),
                        fontsize=6.5,
                        ha="left",
                        va="bottom",
                        xytext=(3, 3),
                        textcoords="offset points",
                        color="#555555",
                    )

            # Trend line
            valid = sub[[wb_col, acc_col]].dropna()
            if len(valid) >= 3:
                z = np.polyfit(valid[wb_col], valid[acc_col], 1)
                p = np.poly1d(z)
                x_line = np.linspace(valid[wb_col].min(), valid[wb_col].max(), 100)
                ax.plot(x_line, p(x_line), "r--", lw=1.2, alpha=0.7)

            # Correlation annotation
            corr_row = df_corr[
                (df_corr["wb_indicator"] == wb_col)
                & (df_corr["access_metric"] == acc_col)
            ]
            if not corr_row.empty and not pd.isna(corr_row["spearman_rho"].iloc[0]):
                rho = corr_row["spearman_rho"].iloc[0]
                pv = corr_row["p_value"].iloc[0]
                sig = corr_row["significance"].iloc[0]
                ax.text(
                    0.97,
                    0.95,
                    f"ρ = {rho:+.3f} {sig}\np = {pv:.3f}  n = {len(valid)}",
                    transform=ax.transAxes,
                    fontsize=8,
                    ha="right",
                    va="top",
                    bbox=dict(
                        boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8
                    ),
                )

            ax.set_xlabel(wb_label, fontsize=9)
            ax.set_ylabel(acc_label, fontsize=9)
            ax.tick_params(labelsize=8)
            ax.grid(alpha=0.25)

    fig.suptitle(
        "Cross-national structural correlation:\n"
        "Development indicators vs climate-driven health accessibility",
        fontsize=13,
        y=1.01,
    )
    plt.tight_layout()
    out_path = out_dir / "structural_scatter_panel.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → structural_scatter_panel.png")


# =============================================================================
# STEP 3 — BUBBLE CHART: GDP × PWMTT × DELTA
# =============================================================================
def plot_bubble_chart(df: pd.DataFrame, out_dir: Path):
    """
    x-axis : GDP per capita (log scale)
    y-axis : PWMTT normal (baseline accessibility)
    bubble size : population
    colour : pwmtt_delta (climate-induced increase)
    """
    sub = df[
        ["country", "gdp_per_capita", "pwmtt_normal", "pwmtt_delta", "population"]
    ].dropna()
    if len(sub) < 5:
        print("  [SKIP] Bubble chart — insufficient complete rows")
        return

    fig, ax = plt.subplots(figsize=(11, 7))

    # Normalise bubble size: sqrt(pop) scaled to [30, 800]
    pop = sub["population"].values
    pop_norm = np.sqrt(pop / pop.max())
    sizes = 30 + pop_norm * 770

    # Colour by pwmtt_delta
    delta = sub["pwmtt_delta"].values
    norm = mcolors.Normalize(vmin=0, vmax=np.percentile(delta, 95))
    cmap = cm.get_cmap("YlOrRd")
    colors = cmap(norm(delta))

    sc = ax.scatter(
        sub["gdp_per_capita"],
        sub["pwmtt_normal"],
        s=sizes,
        c=colors,
        alpha=0.75,
        edgecolors="white",
        lw=0.6,
    )

    # Country labels
    for _, row in sub.iterrows():
        if row["country"] in LABEL_COUNTRIES:
            ax.annotate(
                row["country"],
                (row["gdp_per_capita"], row["pwmtt_normal"]),
                fontsize=8,
                ha="left",
                xytext=(5, 2),
                textcoords="offset points",
                color="#333333",
            )

    ax.set_xscale("log")
    ax.set_xlabel("GDP per capita (USD, log scale)", fontsize=12)
    ax.set_ylabel("Baseline PWMTT — normal weather (hours)", fontsize=12)
    ax.set_title(
        "GDP per capita vs health accessibility\n"
        "Bubble size = population  |  Colour = climate-induced PWMTT increase",
        fontsize=12,
    )
    ax.grid(alpha=0.25)

    # Colourbar
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02)
    cbar.set_label("Climate-induced PWMTT increase (hours)", fontsize=10)

    # Spearman annotation
    rho, pval = spearmanr(np.log(sub["gdp_per_capita"]), sub["pwmtt_normal"])
    ax.text(
        0.03,
        0.96,
        f"Spearman ρ (log GDP vs PWMTT) = {rho:+.3f}  p = {pval:.3f}",
        transform=ax.transAxes,
        fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.8),
    )

    plt.tight_layout()
    out_path = out_dir / "bubble_gdp_pwmtt.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → bubble_gdp_pwmtt.png")


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web" / "network_results" / "structural_correlation"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Structural Correlation Analysis (Direction 1)")
    print(f"{'='*60}")

    df = load_data(base)

    print(f"\n{'='*60}")
    print("  Step 1 — Spearman Correlation Matrix")
    print(f"{'='*60}")
    df_corr = compute_correlations(df, out_dir)

    print(f"\n{'='*60}")
    print("  Step 2 — Scatter Panel")
    print(f"{'='*60}")
    plot_scatter_panel(df, df_corr, out_dir)

    print(f"\n{'='*60}")
    print("  Step 3 — Bubble Chart")
    print(f"{'='*60}")
    plot_bubble_chart(df, out_dir)

    print(f"\n  All outputs in: {out_dir}")


if __name__ == "__main__":
    main()
