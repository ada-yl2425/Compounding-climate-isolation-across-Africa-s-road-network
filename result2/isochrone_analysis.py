"""
isochrone_analysis.py
=====================
Sub-argument 2 — Sections 5.1, 6.2, 6.3 visualisations

Produces three figures:

Figure 1 — isochrone_coverage.png  (Section 5.1 / 6.2)
  Panel A: Grouped bar chart — T60 coverage normal vs extreme for top-20
           countries by shrinkage (WHO 1-hour benchmark).
  Panel B: Heatmap — all countries × 4 thresholds, colour = shrinkage (pp).

Figure 2 — double_vulnerability.png  (Section 5.2 / 6.3)
  Panel A: Histogram of within-country Spearman ρ (baseline t vs Δt)
           across all 50 countries; annotates median and % significant.
  Panel B: Scatter — country median baseline travel time vs
           within-country Spearman ρ; shows that structurally
           worse-off countries also have higher ρ.

Inputs
------
  <BASE_DIR>/web/health_accessibility/country_accessibility_summary.csv

Outputs → <BASE_DIR>/web/network_results/isochrone_analysis/
  isochrone_coverage.png
  double_vulnerability.png

Usage
-----
  python result2/isochrone_analysis.py --base <BASE_DIR>
"""

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import matplotlib.cm as cm
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

warnings.filterwarnings("ignore")

_DEFAULT_BASE = Path("path/to/base")

THRESHOLDS = [30, 60, 120, 240]
THRESH_LABELS = ["30 min", "1 hour", "2 hours", "4 hours"]


def load_data(base: Path) -> pd.DataFrame:
    path = base / "web" / "health_accessibility" / "country_accessibility_summary.csv"
    df = pd.read_csv(path)

    for t in THRESHOLDS:
        n_col = f"isochrone_pct_normal_T{t}min"
        e_col = f"isochrone_pct_extreme_T{t}min"
        df[f"shrink_{t}"] = (df[n_col] - df[e_col]) * 100

    return df


def plot_isochrone_coverage(df: pd.DataFrame, out_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(16, 7))

    ax = axes[0]
    t = 60
    n_col = f"isochrone_pct_normal_T{t}min"
    e_col = f"isochrone_pct_extreme_T{t}min"

    top20 = df.nlargest(20, f"shrink_{t}")[
        ["country", n_col, e_col, f"shrink_{t}"]
    ].sort_values(f"shrink_{t}", ascending=True)

    y = np.arange(len(top20))
    h = 0.35

    bars_n = ax.barh(
        y + h / 2,
        top20[n_col] * 100,
        h,
        color="#4393c3",
        alpha=0.85,
        label="Normal weather",
    )
    bars_e = ax.barh(
        y - h / 2,
        top20[e_col] * 100,
        h,
        color="#d6604d",
        alpha=0.85,
        label="Extreme weather",
    )

    for i, (_, row) in enumerate(top20.iterrows()):
        ax.text(
            max(row[n_col], row[e_col]) * 100 + 0.5,
            i,
            f"−{row[f'shrink_{t}']:.1f} pp",
            va="center",
            fontsize=7,
            color="#555555",
        )

    ax.set_yticks(y)
    ax.set_yticklabels(top20["country"], fontsize=8)
    ax.set_xlabel("Population within 1-hour reach (%)", fontsize=11)
    ax.set_title(
        "WHO 1-hour benchmark: coverage before vs after climate shock\n"
        "Top 20 countries by coverage loss (pp = percentage points)",
        fontsize=10,
    )
    ax.axvline(70, color="gray", lw=0.8, ls="--", alpha=0.6, label="70% reference")
    ax.legend(fontsize=9, loc="lower right")
    ax.set_xlim(0, 115)
    ax.grid(axis="x", alpha=0.2)

    ax2 = axes[1]

    hmap_df = df[["country"] + [f"shrink_{t}" for t in THRESHOLDS]].copy()
    hmap_df = hmap_df.sort_values("shrink_60", ascending=False)
    matrix = hmap_df[[f"shrink_{t}" for t in THRESHOLDS]].values

    vmax = np.nanpercentile(matrix, 95)
    im = ax2.imshow(matrix, aspect="auto", cmap="YlOrRd", vmin=0, vmax=vmax)

    ax2.set_xticks(range(4))
    ax2.set_xticklabels(THRESH_LABELS, fontsize=9)
    ax2.set_yticks(range(len(hmap_df)))
    ax2.set_yticklabels(hmap_df["country"], fontsize=6.5)
    ax2.set_title(
        "Isochrone coverage loss by threshold\n"
        "(percentage-point drop, extreme − normal)",
        fontsize=10,
    )

    cbar = fig.colorbar(im, ax=ax2, pad=0.02, fraction=0.03)
    cbar.set_label("Coverage loss (pp)", fontsize=9)

    crisis = set(df[df[f"isochrone_pct_normal_T60min"] < 0.70]["country"])
    for i, country in enumerate(hmap_df["country"]):
        if country in crisis:
            ax2.get_yticklabels()[i].set_color("#d73027")
            ax2.get_yticklabels()[i].set_fontweight("bold")

    ax2.text(
        1.18,
        0.01,
        "★ Red = structural crisis\n  (baseline <70% at 1h)",
        transform=ax2.transAxes,
        fontsize=7.5,
        color="#d73027",
        va="bottom",
    )

    plt.tight_layout()
    out_path = out_dir / "isochrone_coverage.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → isochrone_coverage.png")


def plot_double_vulnerability(df: pd.DataFrame, out_dir: Path):
    sub = df.dropna(subset=["spearman_rho", "spearman_pval", "pwmtt_normal"]).copy()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]

    rho_vals = sub["spearman_rho"].values
    sig_vals = sub["spearman_pval"].values

    colors_hist = ["#d73027" if p < 0.05 else "#4393c3" for p in sig_vals]
    sorted_idx = np.argsort(rho_vals)

    ax.barh(
        range(len(sub)),
        rho_vals[sorted_idx],
        color=[colors_hist[i] for i in sorted_idx],
        edgecolor="white",
        lw=0.3,
        height=0.8,
    )

    ax.set_yticks(range(len(sub)))
    ax.set_yticklabels(sub["country"].values[sorted_idx], fontsize=6.5)
    ax.axvline(0, color="black", lw=0.8)
    ax.axvline(
        sub["spearman_rho"].median(),
        color="navy",
        lw=1.2,
        ls="--",
        alpha=0.8,
        label=f"Median ρ = {sub['spearman_rho'].median():.3f}",
    )

    n_sig = (sub["spearman_pval"] < 0.05).sum()
    ax.text(
        0.03,
        0.97,
        f"p<0.05: {n_sig}/{len(sub)} countries\n"
        f"Median ρ = {sub['spearman_rho'].median():.4f}",
        transform=ax.transAxes,
        fontsize=9,
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    ax.set_xlabel("Within-country Spearman ρ  (baseline t vs Δt)", fontsize=11)
    ax.set_title(
        "Double-vulnerability test:\nbaseline travel time vs climate-induced increase",
        fontsize=11,
    )
    ax.legend(fontsize=9)
    from matplotlib.patches import Patch

    legend_elements = [
        Patch(facecolor="#d73027", label="p < 0.05 (significant)"),
        Patch(facecolor="#4393c3", label="p ≥ 0.05"),
    ]
    ax.legend(handles=legend_elements, fontsize=9, loc="lower right")
    ax.grid(axis="x", alpha=0.2)

    ax2 = axes[1]

    delta = sub["pwmtt_delta"].values
    norm = mcolors.Normalize(vmin=0, vmax=np.percentile(delta[np.isfinite(delta)], 95))
    cmap = cm.get_cmap("YlOrRd")
    colors_sc = cmap(norm(delta))

    ax2.scatter(
        sub["pwmtt_normal"],
        sub["spearman_rho"],
        s=60,
        c=colors_sc,
        alpha=0.85,
        edgecolors="white",
        lw=0.5,
        zorder=3,
    )

    label_set = {
        "Kenya",
        "Chad",
        "Sudan",
        "Mauritania",
        "Somalia",
        "CongoDR",
        "Nigeria",
        "Ethiopia",
        "Niger",
        "Botswana",
    }
    for _, row in sub.iterrows():
        if row["country"] in label_set:
            ax2.annotate(
                row["country"],
                (row["pwmtt_normal"], row["spearman_rho"]),
                fontsize=7,
                xytext=(4, 2),
                textcoords="offset points",
                color="#333333",
            )

    valid = sub[["pwmtt_normal", "spearman_rho"]].dropna()
    z = np.polyfit(valid["pwmtt_normal"], valid["spearman_rho"], 1)
    x_line = np.linspace(valid["pwmtt_normal"].min(), valid["pwmtt_normal"].max(), 100)
    ax2.plot(x_line, np.poly1d(z)(x_line), "b-", lw=1.5, alpha=0.7)

    rho_meta, pval_meta = spearmanr(valid["pwmtt_normal"], valid["spearman_rho"])
    sig_meta = (
        "***"
        if pval_meta < 0.001
        else ("**" if pval_meta < 0.01 else ("*" if pval_meta < 0.05 else "ns"))
    )
    ax2.text(
        0.97,
        0.03,
        f"ρ(PWMTT, within-ρ) = {rho_meta:+.3f} {sig_meta}\n" f"p = {pval_meta:.3f}",
        transform=ax2.transAxes,
        fontsize=9,
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax2, pad=0.02, fraction=0.046)
    cbar.set_label("Climate-induced PWMTT Δ (hours)", fontsize=9)

    ax2.set_xlabel("Baseline PWMTT (hours)", fontsize=11)
    ax2.set_ylabel("Within-country Spearman ρ", fontsize=11)
    ax2.set_title(
        "Do structurally worse-off countries\nhave stronger double-vulnerability?",
        fontsize=11,
    )
    ax2.grid(alpha=0.2)

    plt.tight_layout()
    out_path = out_dir / "double_vulnerability.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → double_vulnerability.png")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web" / "network_results" / "isochrone_analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Isochrone & Double-Vulnerability Analysis")
    print(f"{'='*60}")

    df = load_data(base)
    print(f"  Countries loaded: {len(df)}")

    print(f"\n{'='*60}")
    print("  Figure 1 — Isochrone Coverage")
    print(f"{'='*60}")
    plot_isochrone_coverage(df, out_dir)

    print(f"\n{'='*60}")
    print("  Figure 2 — Double Vulnerability")
    print(f"{'='*60}")
    plot_double_vulnerability(df, out_dir)

    print(f"\n  All outputs in: {out_dir}")


if __name__ == "__main__":
    main()
