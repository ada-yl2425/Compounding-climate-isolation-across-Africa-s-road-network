"""
subnational_grid_analysis.py
============================
Sub-argument 2 — Directions 1 & 3 at sub-national (grid) resolution

Motivation
----------
Country-level Spearman correlations between World Bank structural indicators
and PWMTT were non-significant (all ns).  The hypothesis is re-tested at a
finer spatial scale: 0.5° grid cells (~56 km at the equator), using the
per-node accessibility outputs already produced by compute_health_accessibility.py.

Analysis
--------
1. Aggregate per-node accessibility data to 0.5° grid cells
   - population-weighted mean t_normal and delta_t per cell
   - facility count from OSM health CSVs → facility_per_million

2. Spearman correlation (cell-level, n ≈ 1,000–2,000):
   - facility_per_million  ×  pw_delta_t
   - road_node_density     ×  pw_delta_t
   - facility_per_million  ×  pw_t_normal
   Produces a small correlation table with ρ, p-value.

3. Scatter plots (2-panel):
   - Left:  facility density vs pw_delta_t  (colour = pw_t_normal)
   - Right: facility density vs pw_t_normal (colour = pw_delta_t)
   Both with Spearman annotation and loess-style trend line.

4. OLS regression:
   pw_delta_t ~ facility_per_million + log1p(pop_density)
   Reports coefficients, R², partial-regression plots.

Inputs
------
  <BASE_DIR>/web/health_accessibility/node_accessibility_{country}.csv
  <BASE_DIR>/RAW/Health_data/{country}_health.csv

Outputs → <BASE_DIR>/web/network_results/subnational_grid/
  grid_cells.csv                all grid cells with computed metrics
  grid_correlation_table.csv    Spearman ρ table
  grid_scatter.png              2-panel scatter
  grid_regression_summary.txt   OLS summary

Usage
-----
  python result2/subnational_grid_analysis.py --base <BASE_DIR>
  python result2/subnational_grid_analysis.py --base <BASE_DIR> --grid-deg 1.0
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
import statsmodels.api as sm

warnings.filterwarnings("ignore")

_DEFAULT_BASE = Path("path/to/base")

# Minimum population per grid cell to include in analysis
POP_MIN = 1_000

# Countries to label on scatter plots
LABEL_CELLS = False  # label individual cells is too noisy; use country centroids


# =============================================================================
# STEP 1 — Load & aggregate node accessibility to grid cells
# =============================================================================
def load_node_data(base: Path) -> pd.DataFrame:
    acc_dir = base / "web" / "health_accessibility"
    frames = []
    for f in sorted(acc_dir.glob("node_accessibility_*.csv")):
        try:
            df = pd.read_csv(f)
            frames.append(df)
        except Exception as e:
            print(f"  [WARN] Could not read {f.name}: {e}")
    if not frames:
        raise FileNotFoundError(f"No node_accessibility_*.csv found in {acc_dir}")
    combined = pd.concat(frames, ignore_index=True)
    print(
        f"  Total nodes loaded: {len(combined):,}  "
        f"({combined['country'].nunique()} countries)"
    )
    return combined


def load_facility_data(base: Path) -> pd.DataFrame:
    health_dir = base / "RAW" / "Health_data"
    frames = []
    for f in sorted(health_dir.glob("*_health.csv")):
        try:
            df = pd.read_csv(f, usecols=["country", "lon", "lat"])
            frames.append(df)
        except Exception as e:
            print(f"  [WARN] Could not read {f.name}: {e}")
    if not frames:
        raise FileNotFoundError(f"No *_health.csv found in {health_dir}")
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["lon", "lat"])
    print(f"  Total facilities loaded: {len(combined):,}")
    return combined


def assign_grid(
    df: pd.DataFrame, deg: float, lon_col: str = "lon", lat_col: str = "lat"
) -> pd.DataFrame:
    df = df.copy()
    df["cell_lon"] = (df[lon_col] / deg).apply(np.floor) * deg + deg / 2
    df["cell_lat"] = (df[lat_col] / deg).apply(np.floor) * deg + deg / 2
    return df


def aggregate_nodes(nodes: pd.DataFrame, deg: float) -> pd.DataFrame:
    """Population-weighted accessibility metrics per grid cell."""
    nodes = assign_grid(nodes, deg)
    nodes = nodes.dropna(subset=["t_normal", "delta_t", "population"])
    nodes = nodes[nodes["population"] > 0]

    def pw_mean(g, col):
        w = g["population"]
        return (g[col] * w).sum() / w.sum()

    agg = (
        nodes.groupby(["cell_lon", "cell_lat"])
        .apply(
            lambda g: pd.Series(
                {
                    "pw_t_normal": pw_mean(g, "t_normal"),
                    "pw_delta_t": pw_mean(g, "delta_t"),
                    "total_pop": g["population"].sum(),
                    "n_nodes": len(g),
                }
            )
        )
        .reset_index()
    )
    return agg


def aggregate_facilities(facilities: pd.DataFrame, deg: float) -> pd.DataFrame:
    facilities = assign_grid(facilities, deg)
    fac_count = (
        facilities.groupby(["cell_lon", "cell_lat"])
        .size()
        .reset_index(name="n_facilities")
    )
    return fac_count


def build_grid(base: Path, deg: float) -> pd.DataFrame:
    print(f"\n  Loading node accessibility files ...")
    nodes = load_node_data(base)

    print(f"  Loading health facility files ...")
    facilities = load_facility_data(base)

    print(f"\n  Aggregating to {deg}° grid ...")
    node_grid = aggregate_nodes(nodes, deg)
    fac_grid = aggregate_facilities(facilities, deg)

    grid = node_grid.merge(fac_grid, on=["cell_lon", "cell_lat"], how="left")
    grid["n_facilities"] = grid["n_facilities"].fillna(0)

    # Facility density
    grid["facility_per_million"] = grid["n_facilities"] / grid["total_pop"] * 1e6

    # Road node density (nodes per 1000 km²)
    lat_rad = np.radians(grid["cell_lat"])
    cell_area_km2 = (deg * 111.0) * (deg * 111.0 * np.cos(lat_rad))
    grid["node_density"] = grid["n_nodes"] / cell_area_km2 * 1e3

    # Filter
    grid = grid[grid["total_pop"] >= POP_MIN].copy()
    grid = grid.dropna(subset=["pw_delta_t", "pw_t_normal", "facility_per_million"])
    grid = grid[np.isfinite(grid["facility_per_million"])]
    grid = grid[np.isfinite(grid["pw_delta_t"])]

    print(f"  Grid cells after filtering (pop≥{POP_MIN:,}): {len(grid):,}")
    return grid


# =============================================================================
# STEP 2 — Spearman correlation table
# =============================================================================
CORR_PAIRS = [
    ("facility_per_million", "pw_delta_t", "Facility density vs climate impact"),
    ("facility_per_million", "pw_t_normal", "Facility density vs baseline travel"),
    ("node_density", "pw_delta_t", "Road density vs climate impact"),
    ("node_density", "pw_t_normal", "Road density vs baseline travel"),
]


def compute_correlations(grid: pd.DataFrame, out_dir: Path) -> pd.DataFrame:
    records = []
    print("\n  Spearman correlations (grid-cell level):")
    for x_col, y_col, label in CORR_PAIRS:
        sub = grid[[x_col, y_col]].dropna()
        sub = sub[np.isfinite(sub[x_col]) & np.isfinite(sub[y_col])]
        rho, pval = spearmanr(sub[x_col], sub[y_col])
        sig = (
            "***"
            if pval < 0.001
            else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
        )
        print(f"    {label:<45}  ρ={rho:+.3f}  p={pval:.4f} {sig}  n={len(sub):,}")
        records.append(
            dict(
                x=x_col,
                y=y_col,
                label=label,
                n=len(sub),
                rho=round(rho, 4),
                p_value=round(pval, 6),
                significance=sig,
            )
        )
    df = pd.DataFrame(records)
    df.to_csv(out_dir / "grid_correlation_table.csv", index=False)
    print(f"  Saved → grid_correlation_table.csv")
    return df


# =============================================================================
# STEP 3 — Scatter plots
# =============================================================================
def plot_scatter(grid: pd.DataFrame, out_dir: Path):
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # --- clip extreme outliers for display ---
    q99_fac = grid["facility_per_million"].quantile(0.99)
    q99_delta = grid["pw_delta_t"].quantile(0.99)
    q99_base = grid["pw_t_normal"].quantile(0.99)
    g = grid[
        (grid["facility_per_million"] <= q99_fac)
        & (grid["pw_delta_t"] <= q99_delta)
        & (grid["pw_t_normal"] <= q99_base)
    ].copy()

    # --- Left panel: facility density vs pw_delta_t ---
    ax = axes[0]
    norm = mcolors.Normalize(vmin=0, vmax=np.percentile(g["pw_t_normal"], 95))
    cmap = cm.get_cmap("YlOrRd")
    colors = cmap(norm(g["pw_t_normal"].values))

    ax.scatter(
        g["facility_per_million"], g["pw_delta_t"], s=6, c=colors, alpha=0.5, lw=0
    )

    # Trend line
    valid = g[["facility_per_million", "pw_delta_t"]].dropna()
    z = np.polyfit(valid["facility_per_million"], valid["pw_delta_t"], 1)
    x_line = np.linspace(
        valid["facility_per_million"].min(), valid["facility_per_million"].max(), 200
    )
    ax.plot(x_line, np.poly1d(z)(x_line), "b-", lw=1.5, alpha=0.8)

    rho, pval = spearmanr(valid["facility_per_million"], valid["pw_delta_t"])
    sig = (
        "***"
        if pval < 0.001
        else ("**" if pval < 0.01 else ("*" if pval < 0.05 else "ns"))
    )
    ax.text(
        0.97,
        0.97,
        f"ρ = {rho:+.3f} {sig}\np = {pval:.4f}  n = {len(valid):,}",
        transform=ax.transAxes,
        fontsize=9,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, pad=0.02, fraction=0.046)
    cbar.set_label("Baseline travel time (hours)", fontsize=8)

    ax.set_xlabel("Health facilities per million people (0.5° cell)", fontsize=10)
    ax.set_ylabel("Pop-weighted climate impact Δt (hours)", fontsize=10)
    ax.set_title(
        "Facility density vs climate impact\n" "Colour = baseline travel time",
        fontsize=10,
    )
    ax.grid(alpha=0.2)

    # --- Right panel: facility density vs pw_t_normal ---
    ax2 = axes[1]
    norm2 = mcolors.Normalize(vmin=0, vmax=np.percentile(g["pw_delta_t"], 95))
    colors2 = cmap(norm2(g["pw_delta_t"].values))

    ax2.scatter(
        g["facility_per_million"], g["pw_t_normal"], s=6, c=colors2, alpha=0.5, lw=0
    )

    valid2 = g[["facility_per_million", "pw_t_normal"]].dropna()
    z2 = np.polyfit(valid2["facility_per_million"], valid2["pw_t_normal"], 1)
    x_line2 = np.linspace(
        valid2["facility_per_million"].min(), valid2["facility_per_million"].max(), 200
    )
    ax2.plot(x_line2, np.poly1d(z2)(x_line2), "b-", lw=1.5, alpha=0.8)

    rho2, pval2 = spearmanr(valid2["facility_per_million"], valid2["pw_t_normal"])
    sig2 = (
        "***"
        if pval2 < 0.001
        else ("**" if pval2 < 0.01 else ("*" if pval2 < 0.05 else "ns"))
    )
    ax2.text(
        0.97,
        0.97,
        f"ρ = {rho2:+.3f} {sig2}\np = {pval2:.4f}  n = {len(valid2):,}",
        transform=ax2.transAxes,
        fontsize=9,
        ha="right",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", facecolor="lightyellow", alpha=0.9),
    )

    sm2 = plt.cm.ScalarMappable(cmap=cmap, norm=norm2)
    sm2.set_array([])
    cbar2 = fig.colorbar(sm2, ax=ax2, pad=0.02, fraction=0.046)
    cbar2.set_label("Climate impact Δt (hours)", fontsize=8)

    ax2.set_xlabel("Health facilities per million people (0.5° cell)", fontsize=10)
    ax2.set_ylabel("Pop-weighted baseline travel time (hours)", fontsize=10)
    ax2.set_title(
        "Facility density vs baseline accessibility\n" "Colour = climate impact",
        fontsize=10,
    )
    ax2.grid(alpha=0.2)

    plt.tight_layout()
    out_path = out_dir / "grid_scatter.png"
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved → grid_scatter.png")


# =============================================================================
# STEP 4 — OLS regression
# =============================================================================
def run_regression(grid: pd.DataFrame, out_dir: Path):
    reg = (
        grid[["pw_delta_t", "facility_per_million", "total_pop", "pw_t_normal"]]
        .dropna()
        .copy()
    )
    reg = reg[np.isfinite(reg).all(axis=1)]
    reg = reg[reg["facility_per_million"] >= 0]
    reg = reg[reg["total_pop"] > 0]

    reg["log_pop_density"] = np.log1p(reg["total_pop"])
    reg["log_facility"] = np.log1p(reg["facility_per_million"])

    X = sm.add_constant(reg[["log_facility", "log_pop_density"]])
    y = reg["pw_delta_t"]

    model = sm.OLS(y, X).fit()
    summary_text = model.summary().as_text()

    out_path = out_dir / "grid_regression_summary.txt"
    with open(out_path, "w") as f:
        f.write("OLS Regression: pw_delta_t ~ log(facility/M) + log(population)\n")
        f.write(f"n = {len(reg):,}  grid cells\n\n")
        f.write(summary_text)

    print(f"\n  OLS Regression Summary:")
    print(
        f"    n = {len(reg):,}  R² = {model.rsquared:.4f}  "
        f"adj-R² = {model.rsquared_adj:.4f}"
    )
    for name, coef, pv in zip(
        model.params.index, model.params.values, model.pvalues.values
    ):
        sig = (
            "***"
            if pv < 0.001
            else ("**" if pv < 0.01 else ("*" if pv < 0.05 else "ns"))
        )
        print(f"    {name:<25} coef={coef:+.5f}  p={pv:.4f} {sig}")
    print(f"  Saved → grid_regression_summary.txt")


# =============================================================================
# MAIN
# =============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default=str(_DEFAULT_BASE))
    parser.add_argument(
        "--grid-deg",
        type=float,
        default=0.5,
        help="Grid cell size in degrees (default 0.5)",
    )
    args = parser.parse_args()

    base = Path(args.base)
    out_dir = base / "web" / "network_results" / "subnational_grid"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  Sub-national Grid Analysis  ({args.grid_deg}° cells)")
    print(f"{'='*60}")

    grid = build_grid(base, args.grid_deg)
    grid.to_csv(out_dir / "grid_cells.csv", index=False)
    print(f"  Saved → grid_cells.csv  ({len(grid):,} cells)")

    print(f"\n{'='*60}")
    print("  Step 2 — Spearman Correlations")
    print(f"{'='*60}")
    compute_correlations(grid, out_dir)

    print(f"\n{'='*60}")
    print("  Step 3 — Scatter Plots")
    print(f"{'='*60}")
    plot_scatter(grid, out_dir)

    print(f"\n{'='*60}")
    print("  Step 4 — OLS Regression")
    print(f"{'='*60}")
    run_regression(grid, out_dir)

    print(f"\n  All outputs in: {out_dir}")


if __name__ == "__main__":
    main()
