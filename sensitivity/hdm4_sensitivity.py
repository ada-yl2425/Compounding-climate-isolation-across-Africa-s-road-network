"""
sensitivity/hdm4_sensitivity.py
=========================
Robustness / sensitivity analysis for HDM-4 preset parameter choices.

Method
------
Morris Elementary Effects (SALib) on 3 000 synthetic Africa-calibrated road
segments.  No real climate or road data required — every evaluation is a
pure NumPy computation (runs in seconds).

If SALib is not installed the script falls back to One-At-a-Time (OAT) only.
    pip install SALib

Parameters tested (8 total)
----------------------------
NL      light vehicles day⁻¹          baseline 42    range [10, 80]
NH      heavy vehicles day⁻¹          baseline  8    range [ 2, 30]
N_cov   N_total in precip covariate   baseline 50    range [20,100]
MGD     mean gravel depth (m)         baseline  0.5  range [0.2, 0.8]
IRI_min lower-bound roughness (m/km)  baseline 12.0  range [ 8, 16]
IRI_0   initial IRI at t=0 (m/km)    baseline  6.0  range [ 4, 14]
P_norm  passable-percentile (%)       baseline 75    range [65, 85]
P_extr  extreme-percentile  (%)       baseline 95    range [88, 99]

Output metrics (4)
------------------
V_normal   mean effective speed, normal scenario (km/h)
V_extreme  mean effective speed, extreme scenario (km/h)
delta_pct  mean (V_normal − V_extreme)/V_normal × 100  ← paper's core signal
p_block    mean blocking probability under extreme

Outputs saved
-------------
sensitivity/hdm4_morris_sensitivity.png
sensitivity/hdm4_oat_sensitivity.png
sensitivity/hdm4_sensitivity_table.csv
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).parent


try:
    from SALib.sample.morris import sample as morris_sample
    from SALib.analyze.morris import analyze as morris_analyze

    HAS_SALIB = True
except ImportError:
    HAS_SALIB = False
    print("[WARN] SALib not found — Morris analysis skipped.")
    print("       Install with:  pip install SALib\n")


_R = np.array([6, 8, 10, 12, 14, 16, 18, 20], dtype=float)
_V = np.array([106, 80, 64, 53, 46, 40, 35, 32], dtype=float)


def iri_to_speed(iri: np.ndarray) -> np.ndarray:
    return np.interp(np.clip(iri, _R[0], _R[-1]), _R, _V)


def hdm4_iri_vec(
    mmp_m: np.ndarray,
    kcv: np.ndarray,
    slope_pct: np.ndarray,
    NL: float,
    NH: float,
    N_cov: float,
    MGD: float,
    IRI_min: float,
    IRI_0: float,
    dt: float = 1 / 12,
) -> np.ndarray:
    """Return annual equilibrium IRI for each road segment (vectorised)."""
    rg_max = np.maximum(
        21.4 - 32.4 * (0.5 - MGD) ** 2 + 0.97 * kcv - 7.64 * slope_pct * mmp_m,
        IRI_min,
    )
    p = np.exp(
        -0.001 * (0.461 + 0.0174 * NL + 0.0114 * NH - 0.0287 * N_cov * mmp_m) * dt
    )
    rg = np.full_like(rg_max, IRI_0)
    for _ in range(12):
        rg = rg_max - p * (rg_max - rg)
    return rg


RNG = np.random.default_rng(42)
N_SEGS = 3_000
N_MONTHS = 120


def _make_synthetic_data() -> dict:
    """Generate fixed synthetic segments used throughout the analysis."""
    kcv = RNG.uniform(0, 80, N_SEGS)
    slope_deg = RNG.exponential(scale=3.0, size=N_SEGS).clip(0.1, 15)
    slope_pct = np.tan(np.radians(slope_deg)) * 100

    pr = RNG.lognormal(mean=np.log(0.035), sigma=0.9, size=(N_MONTHS, N_SEGS)).clip(
        1e-6
    )
    mmp_normal = pr.mean(axis=0)
    mmp_extreme = np.percentile(pr, 95, axis=0)

    mrso = RNG.lognormal(mean=np.log(40), sigma=0.6, size=(N_MONTHS, N_SEGS)).clip(0)

    return dict(
        kcv=kcv,
        slope_pct=slope_pct,
        mmp_normal=mmp_normal,
        mmp_extreme=mmp_extreme,
        mrso=mrso,
    )


SEGS = _make_synthetic_data()


BASELINE = dict(
    NL=42.0,
    NH=8.0,
    N_cov=50.0,
    MGD=0.5,
    IRI_min=12.0,
    IRI_0=6.0,
    P_norm=75.0,
    P_extr=95.0,
)


def compute_metrics(
    NL, NH, N_cov, MGD, IRI_min, IRI_0, P_norm, P_extr
) -> tuple[float, float, float, float]:
    """
    Evaluate one parameter combination on the fixed synthetic dataset.

    Returns
    -------
    (mean_V_normal, mean_V_extreme, mean_delta_pct, mean_p_block)
    """
    kcv = SEGS["kcv"]
    slope_pct = SEGS["slope_pct"]
    mrso = SEGS["mrso"]

    iri_n = hdm4_iri_vec(
        SEGS["mmp_normal"], kcv, slope_pct, NL, NH, N_cov, MGD, IRI_min, IRI_0
    )
    iri_e = hdm4_iri_vec(
        SEGS["mmp_extreme"], kcv, slope_pct, NL, NH, N_cov, MGD, IRI_min, IRI_0
    )

    v_base_n = iri_to_speed(iri_n)
    v_base_e = iri_to_speed(iri_e)

    mrso_pN = np.percentile(mrso, P_norm, axis=0)
    mrso_pE = np.percentile(mrso, P_extr, axis=0)

    passable_n = (mrso <= mrso_pN).mean(axis=0)
    ratio = np.where(mrso_pE > mrso_pN, mrso_pN / np.maximum(mrso_pE, 1e-6), 1.0)
    passable_e = passable_n * ratio

    V_n = v_base_n * passable_n
    V_e = v_base_e * passable_e

    mean_V_n = float(V_n.mean())
    mean_V_e = float(V_e.mean())

    mask = V_n > 0
    delta = np.where(mask, (V_n - V_e) / np.where(mask, V_n, 1.0) * 100, np.nan)
    mean_delta = float(np.nanmean(delta))
    mean_p_block = float((1 - passable_e).mean())

    return mean_V_n, mean_V_e, mean_delta, mean_p_block


OUTPUT_NAMES = ["V_normal (km/h)", "V_extreme (km/h)", "ΔV (%)", "p_block"]

PROBLEM = {
    "num_vars": 8,
    "names": ["NL", "NH", "N_cov", "MGD", "IRI_min", "IRI_0", "P_norm", "P_extr"],
    "bounds": [
        [10, 80],
        [2, 30],
        [20, 100],
        [0.2, 0.8],
        [8.0, 16.0],
        [4.0, 14.0],
        [65, 85],
        [88, 99],
    ],
}

if HAS_SALIB:
    print("Running Morris analysis  (r=20 → 180 evaluations) …")
    param_samples = morris_sample(PROBLEM, N=20, num_levels=4, seed=42)

    Y = np.array([compute_metrics(*p) for p in param_samples])

    morris_rows: list[dict] = []
    for col, out_name in enumerate(OUTPUT_NAMES):
        Si = morris_analyze(PROBLEM, param_samples, Y[:, col], print_to_console=False)
        for j, pname in enumerate(PROBLEM["names"]):
            morris_rows.append(
                dict(
                    output=out_name,
                    parameter=pname,
                    mu_star=float(Si["mu_star"][j]),
                    sigma=float(Si["sigma"][j]),
                )
            )

    df_morris = pd.DataFrame(morris_rows)

    fig, axes = plt.subplots(2, 2, figsize=(11, 9))
    for ax, out_name in zip(axes.ravel(), OUTPUT_NAMES):
        sub = df_morris[df_morris["output"] == out_name]
        ax.scatter(sub["mu_star"], sub["sigma"], s=90, color="steelblue", zorder=3)
        for _, row in sub.iterrows():
            ax.annotate(
                row["parameter"],
                (row["mu_star"], row["sigma"]),
                textcoords="offset points",
                xytext=(5, 3),
                fontsize=9,
            )
        top = max(sub["mu_star"].max(), sub["sigma"].max()) * 1.25 + 1e-9
        ax.plot([0, top], [0, top], "k--", lw=0.8, alpha=0.4, label="σ = μ*")
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("μ*  (mean |elementary effect|)", fontsize=9)
        ax.set_ylabel("σ  (std of elementary effects)", fontsize=9)
        ax.set_title(f"Morris diagram — {out_name}", fontsize=10, fontweight="bold")
        ax.grid(alpha=0.25)
        ax.legend(fontsize=8)

    plt.suptitle(
        "HDM-4 preset sensitivity  (Morris method, r = 20)\n"
        f"N = {N_SEGS:,} synthetic Africa road segments",
        fontsize=11,
    )
    plt.tight_layout()
    out_morris = OUT_DIR / "hdm4_morris_sensitivity.png"
    plt.savefig(out_morris, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  → {out_morris}")

    pivot = df_morris.pivot(index="parameter", columns="output", values="mu_star")
    pivot = pivot.sort_values("ΔV (%)", ascending=False)
    print("\nMorris μ*  (higher = more influential)\n", pivot.round(4).to_string())


print("\nRunning OAT analysis …")

OAT_GRID: dict[str, tuple[np.ndarray, str]] = {
    "NL": (np.linspace(10, 80, 20), "N_L  (light veh day⁻¹)"),
    "NH": (np.linspace(2, 30, 20), "N_H  (heavy veh day⁻¹)"),
    "N_cov": (np.linspace(20, 100, 20), "N_total covariate"),
    "MGD": (np.linspace(0.2, 0.8, 20), "Mean gravel depth (m)"),
    "IRI_min": (np.linspace(8, 16, 20), "IRI_min  (m km⁻¹)"),
    "IRI_0": (np.linspace(4, 14, 20), "IRI₀  (m km⁻¹)"),
    "P_norm": (np.linspace(65, 85, 20), "P_normal  (%)"),
    "P_extr": (np.linspace(88, 99, 20), "P_extreme (%)"),
}

oat_rows: list[dict] = []
fig, axes = plt.subplots(4, 2, figsize=(12, 14))
axes_flat = axes.ravel()

for ax_i, (param, (values, xlabel)) in enumerate(OAT_GRID.items()):
    ax = axes_flat[ax_i]
    ax2 = ax.twinx()

    deltas, p_blocks, v_normals = [], [], []
    for v in values:
        kw = {**BASELINE, param: v}
        vn, _, dv, pb = compute_metrics(**kw)
        deltas.append(dv)
        p_blocks.append(pb)
        v_normals.append(vn)
        oat_rows.append(
            {"param": param, "value": v, "V_normal": vn, "delta_pct": dv, "p_block": pb}
        )

    bl = BASELINE[param]
    (l1,) = ax.plot(
        values, deltas, "o-", color="steelblue", ms=4, lw=1.5, label="ΔV (%)"
    )
    (l2,) = ax2.plot(
        values, p_blocks, "s--", color="tomato", ms=4, lw=1.5, label="p_block"
    )
    ax.axvline(bl, ls=":", color="gray", lw=1.5, alpha=0.7)

    ax.set_xlabel(xlabel, fontsize=9)
    ax.set_ylabel("ΔV (%)", color="steelblue", fontsize=9)
    ax2.set_ylabel("p_block", color="tomato", fontsize=9)
    ax.tick_params(axis="y", labelcolor="steelblue")
    ax2.tick_params(axis="y", labelcolor="tomato")
    ax.set_title(f"{param}  [baseline = {bl}]", fontsize=10, fontweight="bold")
    ax.grid(alpha=0.25)
    if ax_i == 0:
        ax.legend([l1, l2], ["ΔV (%)", "p_block"], fontsize=8, loc="upper right")

plt.suptitle(
    "One-At-a-Time sensitivity  —  HDM-4 presets\n"
    "(vertical dashed line = baseline; all other parameters held fixed)",
    fontsize=11,
)
plt.tight_layout()
out_oat = OUT_DIR / "hdm4_oat_sensitivity.png"
plt.savefig(out_oat, dpi=150, bbox_inches="tight")
plt.close()
print(f"  → {out_oat}")


df_oat = pd.DataFrame(oat_rows)


def _baseline_val(g: pd.DataFrame) -> float:
    bl = BASELINE[g.name]
    return float(g.loc[(g["value"] - bl).abs().idxmin(), "delta_pct"])


summary = pd.DataFrame(
    {
        "baseline_delta_pct": df_oat.groupby("param").apply(
            _baseline_val, include_groups=False
        ),
        "min_delta_pct": df_oat.groupby("param")["delta_pct"].min(),
        "max_delta_pct": df_oat.groupby("param")["delta_pct"].max(),
        "range_delta_pct": df_oat.groupby("param")["delta_pct"].agg(
            lambda x: x.max() - x.min()
        ),
        "min_p_block": df_oat.groupby("param")["p_block"].min(),
        "max_p_block": df_oat.groupby("param")["p_block"].max(),
        "range_p_block": df_oat.groupby("param")["p_block"].agg(
            lambda x: x.max() - x.min()
        ),
    }
)
summary["sensitivity_rank"] = (
    summary["range_delta_pct"].rank(ascending=False).astype(int)
)
summary = summary.sort_values("sensitivity_rank")

out_csv = OUT_DIR / "hdm4_sensitivity_table.csv"
summary.round(4).to_csv(out_csv)

print("\n── Robustness table (sorted by sensitivity on ΔV%) ──")
print(summary.round(4).to_string())
print(f"\n  → {out_csv}")

print(
    "\nDone.\n"
    f"  Morris diagram : {OUT_DIR / 'hdm4_morris_sensitivity.png'}\n"
    f"  OAT curves     : {OUT_DIR / 'hdm4_oat_sensitivity.png'}\n"
    f"  Summary table  : {OUT_DIR / 'hdm4_sensitivity_table.csv'}\n"
)
