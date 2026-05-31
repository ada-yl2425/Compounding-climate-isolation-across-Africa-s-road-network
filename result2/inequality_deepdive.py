"""
inequality_deepdive.py
======================
Sub-argument 2 — Inequality Deep-dive

Two complementary analyses using already-computed columns in
country_accessibility_summary.csv:

Panel A — Tail amplification (tail_gap_ratio)
  p90_delta vs p50_delta scatter, annotated with 1:1 and 3:1 reference lines.
  Every country above the 1:1 line = worst-off quintile suffers more than the
  median.  The further above, the more unequal the within-country distribution
  of climate burden.

Panel B — Gini change (delta_gini)
  Pre-existing within-country inequality (gini_normal) vs change in Gini after
  climate shock (delta_gini).  A positive relationship would mean already-
  unequal countries become more unequal.  Also shows a ranked bar of delta_gini
  to identify which countries' internal inequality worsens most.

Inputs
------
  <BASE_DIR>/web/health_accessibility/country_accessibility_summary.csv

Outputs → <BASE_DIR>/web/network_results/inequality_deepdive/
  tail_amplification.png     p90 vs p50 delta scatter (Panel A)
  gini_change.png            gini_normal vs delta_gini + bar chart (Panel B)
  inequality_stats.csv       key numbers used in both panels

Usage
-----
  python result2/inequality_deepdive.py --base <BASE_DIR>
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

LABEL_COUNTRIES = {
    "Kenya",
    "Chad",
    "Mauritania",
    "Somalia",
    "Niger",
    "Sudan",
    "Nigeria",
    "CongoDR",
    "BurkinaFaso",
    "IvoryCoast",
    "Egypt",
    "Tunisia",
    "Djibouti",
    "WestSahara",
    "Botswana",
    "Ethiopia",
}


def load_data(base: Path) -> pd.DataFrame:
    path = base / "web" / "health_accessibility" / "country_accessibility_summary.csv"
    df = pd.read_csv(path)

    df["tail_gap_ratio_plot"] = df["tail_gap_ratio"].fillna(1.0)

    df = df[df["country"] != "WestSahara"].copy()
    print(f"  Countries loaded: {len(df)}")
    return df


def plot_tail_amplification(df: pd.DataFrame, out_dir: Path):
    """
    Scatter: x = p50_delta_h (median climate impact),
             y = p90_delta_h (90th-pctile climate impact)
    Reference lines: 1:1 (equal distribution) and 3:1 (3x tail amplification)
    Colour: tail_gap_ratio_plot
    """
    sub = df.dropna(subset=["p50_delta_h", "p90_delta_h"]).copy()
    sub = sub[sub["p50_delta_h"] >= 0]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]

    tgr = sub["tail_gap_ratio_plot"].values
    norm = mcolors.Normalize(vmin=1, vmax=np.percentile(tgr[np.isfinite(tgr)], 95))
    cmap = cm.get_cmap("YlOrRd")
    colors = cmap(norm(tgr))

    ax.scatter(
        sub["p50_delta_h"],
        sub["p90_delta_h"],
        s=60,
        c=colors,
        alpha=0.85,
        edgecolors="white",
        lw=0.6,
        zorder=3,
    )

    x_max = sub["p90_delta_h"].max() * 1.05
    x_ref = np.linspace(0, sub["p50_delta_h"].max() * 1.05, 200)
    ax.plot(x_ref, x_ref, "k--", lw=1.0, alpha=0.4, label="1:1 (equal impact)")
    ax.plot(x_ref, 3 * x_ref, "b--", lw=1.0, alpha=0.5, label="3:1 (p90 = 3×p50)")
    ax.plot(x_ref, 5 * x_ref, "r--", lw=1.0, alpha=0.4, label="5:1")

    for _, row in sub.iterrows():
        if row["country"] in LABEL_COUNTRIES:
            ax.annotate(
                row["country"],
                (row["p50_delta_h"], row["p90_delta_h"]),
                fontsize=7,
                ha="left",
                xytext=(4, 2),
                textcoords="offset points",
                color="#333333",
            )

    ax.set_xlabel("Median climate impact — p50 Δt (hours)", fontsize=11)
    ax.set_ylabel("90th-pctile climate impact — p90 Δt (hours)", fontsize=11)
    ax.set_title(
        "Within-country tail amplification\n"
        "Countries above 1:1 line: worst-off face more than median",
        fontsize=11,
    )
    ax.legend(fontsize=8, loc="upper left")

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label("Tail-gap ratio  (p90Δ / p50Δ)", fontsize=9)
    ax.grid(alpha=0.2)

    valid = sub[["p50_delta_h", "tail_gap_ratio_plot"]].dropna()
    valid = valid[valid["p50_delta_h"] > 0]
    if len(valid) >= 5:
        rho, pval = spearmanr(valid["p50_delta_h"], valid["tail_gap_ratio_plot"])
        sig = (
            "***"
            if pval < 0.001
            else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
        )
        ax.text(
            0.97,
            0.03,
            f"ρ(p50Δ, tail-gap) = {rho:+.3f} {sig}\np = {pval:.3f}",
            transform=ax.transAxes,
            fontsize=8,
            ha="right",
            va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.85),
        )

    ax2 = axes[1]
    bar_df = sub[["country", "tail_gap_ratio_plot", "pwmtt_normal"]].copy()
    bar_df = bar_df.sort_values("tail_gap_ratio_plot", ascending=True)

    norm2 = mcolors.Normalize(
        vmin=bar_df["pwmtt_normal"].min(), vmax=bar_df["pwmtt_normal"].quantile(0.95)
    )
    bar_colors = [cmap(norm2(v)) for v in bar_df["pwmtt_normal"].values]

    bars = ax2.barh(
        bar_df["country"],
        bar_df["tail_gap_ratio_plot"],
        color=bar_colors,
        edgecolor="white",
        lw=0.4,
    )
    ax2.axvline(1, color="black", lw=0.8, ls="--", alpha=0.5, label="1:1 baseline")
    ax2.axvline(3, color="gray", lw=0.8, ls=":", alpha=0.5, label="3:1 reference")

    sm2 = plt.cm.ScalarMappable(cmap=cmap, norm=norm2)
    sm2.set_array([])
    cbar2 = fig.colorbar(sm2, ax=ax2, pad=0.02, fraction=0.046)
    cbar2.set_label("Baseline PWMTT (hours)", fontsize=9)

    ax2.set_xlabel("Tail-gap ratio  (p90Δt / p50Δt)", fontsize=11)
    ax2.set_title(
        "Within-country climate burden inequality\n"
        "Colour = baseline accessibility (darker = worse)",
        fontsize=11,
    )
    ax2.legend(fontsize=8)
    ax2.tick_params(axis="y", labelsize=7)
    ax2.grid(axis="x", alpha=0.2)

    plt.tight_layout()
    out_path = out_dir / "tail_amplification.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → tail_amplification.png")


def plot_gini_change(df: pd.DataFrame, out_dir: Path):
    sub = df.dropna(subset=["gini_normal", "delta_gini"]).copy()

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]

    delta = sub["pwmtt_delta"].values
    norm = mcolors.Normalize(vmin=0, vmax=np.percentile(delta[np.isfinite(delta)], 95))
    cmap = cm.get_cmap("YlOrRd")
    colors = cmap(norm(delta))

    ax.scatter(
        sub["gini_normal"],
        sub["delta_gini"],
        s=60,
        c=colors,
        alpha=0.85,
        edgecolors="white",
        lw=0.6,
        zorder=3,
    )
    ax.axhline(
        0, color="black", lw=0.8, ls="--", alpha=0.5, label="No change (Δ Gini = 0)"
    )

    for _, row in sub.iterrows():
        if row["country"] in LABEL_COUNTRIES:
            ax.annotate(
                row["country"],
                (row["gini_normal"], row["delta_gini"]),
                fontsize=7,
                ha="left",
                xytext=(4, 2),
                textcoords="offset points",
                color="#333333",
            )

    z = np.polyfit(sub["gini_normal"], sub["delta_gini"], 1)
    x_line = np.linspace(sub["gini_normal"].min(), sub["gini_normal"].max(), 100)
    ax.plot(x_line, np.poly1d(z)(x_line), "b-", lw=1.5, alpha=0.7)

    rho, pval = spearmanr(sub["gini_normal"], sub["delta_gini"])
    sig = (
        "***"
        if pval < 0.001
        else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
    )
    ax.text(
        0.97,
        0.97,
        f"ρ = {rho:+.3f} {sig}\np = {pval:.3f}  n = {len(sub)}",
        transform=ax.transAxes,
        fontsize=9,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.85),
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label("Climate-induced PWMTT Δ (hours)", fontsize=9)

    ax.set_xlabel(
        "Pre-climate Gini (within-country travel time inequality)", fontsize=11
    )
    ax.set_ylabel("Δ Gini after climate shock", fontsize=11)
    ax.set_title(
        "Does existing inequality predict worsening?\n"
        "Colour = magnitude of climate impact",
        fontsize=11,
    )
    ax.legend(fontsize=8)
    ax.grid(alpha=0.2)

    ax2 = axes[1]
    bar_df = sub[["country", "delta_gini", "pwmtt_normal"]].copy()
    bar_df = bar_df.sort_values("delta_gini", ascending=True)

    bar_colors = [
        "#d73027" if v > 0 else "#4575b4" for v in bar_df["delta_gini"].values
    ]

    ax2.barh(
        bar_df["country"],
        bar_df["delta_gini"],
        color=bar_colors,
        edgecolor="white",
        lw=0.4,
    )
    ax2.axvline(0, color="black", lw=0.8)

    n_pos = (bar_df["delta_gini"] > 0).sum()
    n_neg = (bar_df["delta_gini"] <= 0).sum()
    ax2.text(
        0.97,
        0.03,
        f"Gini increases: {n_pos} countries\nGini decreases: {n_neg} countries",
        transform=ax2.transAxes,
        fontsize=8,
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.85),
    )

    ax2.set_xlabel("Δ Gini  (extreme − normal)", fontsize=11)
    ax2.set_title(
        "Within-country travel time inequality change\n"
        "Red = more unequal after climate shock",
        fontsize=11,
    )
    ax2.tick_params(axis="y", labelsize=7)
    ax2.grid(axis="x", alpha=0.2)

    plt.tight_layout()
    out_path = out_dir / "gini_change.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → gini_change.png")


def save_stats(df: pd.DataFrame, out_dir: Path):
    cols = [
        "country",
        "pwmtt_normal",
        "pwmtt_delta",
        "tail_gap_ratio_plot",
        "p50_delta_h",
        "p90_delta_h",
        "gini_normal",
        "gini_extreme",
        "delta_gini",
    ]
    out = df[cols].copy().sort_values("tail_gap_ratio_plot", ascending=False)
    out.to_csv(out_dir / "inequality_stats.csv", index=False)
    print(f"  Saved → inequality_stats.csv")

    print(f"\n  Key numbers:")
    print(
        f"    Countries where Gini increases: "
        f"{(df['delta_gini'] > 0).sum()} / {len(df)}"
    )
    print(f"    Median tail-gap ratio: " f"{df['tail_gap_ratio_plot'].median():.2f}")
    print(f"    Mean tail-gap ratio:   " f"{df['tail_gap_ratio_plot'].mean():.2f}")
    top5 = df.nlargest(5, "tail_gap_ratio_plot")[["country", "tail_gap_ratio_plot"]]
    print(f"    Top-5 tail-gap countries:")
    for _, row in top5.iterrows():
        print(f"      {row['country']:<18} {row['tail_gap_ratio_plot']:.2f}×")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web" / "network_results" / "inequality_deepdive"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print("  Inequality Deep-dive (Tail + Gini)")
    print(f"{'='*60}")

    df = load_data(base)

    print(f"\n{'='*60}")
    print("  Panel A — Tail Amplification")
    print(f"{'='*60}")
    plot_tail_amplification(df, out_dir)

    print(f"\n{'='*60}")
    print("  Panel B — Gini Change")
    print(f"{'='*60}")
    plot_gini_change(df, out_dir)

    print(f"\n{'='*60}")
    print("  Summary Stats")
    print(f"{'='*60}")
    save_stats(df, out_dir)

    print(f"\n  All outputs in: {out_dir}")


if __name__ == "__main__":
    main()
