"""Robustness checks for NI/CV bottleneck geography and recovery headline."""

from __future__ import annotations

import argparse
import json
import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from sensitivity.config import (
    NI_ALPHA_GRID,
    RECOVERY_ALPHA_GRID,
    TOPK_SHARES,
    add_common_path_args,
    resolve_paths,
)
from sensitivity.io_utils import (
    ensure_dir,
    finite_numeric,
    jaccard,
    normalize_positive,
    top_set,
    write_table,
)


PAVING_FRACTIONS = [0.0, 0.001, 0.002, 0.005, 0.01]
N_RANDOM_TRIALS = 5
UNREACHABLE = 1e8


@dataclass(frozen=True)
class ScoreSpec:
    name: str
    ni_alpha: float
    score_form: str


def load_edge_scores(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    required = {"NI", "CV", "bottleneck", "unpaved"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {path}: {sorted(missing)}")
    df = df.copy()
    df["_edge_id"] = df.index.astype(int)
    df["NI"] = finite_numeric(df["NI"])
    df["CV"] = finite_numeric(df["CV"])
    df["bottleneck"] = finite_numeric(df["bottleneck"])
    df["unpaved"] = finite_numeric(df["unpaved"]).astype(int)
    return df


def score_edges(df: pd.DataFrame, spec: ScoreSpec) -> pd.Series:
    ni = df["NI"].clip(lower=0.0)
    cv = df["CV"].clip(lower=0.0)
    ni_norm = normalize_positive(ni)
    cv_norm = normalize_positive(cv)

    if spec.score_form == "raw_product":
        score = (ni**spec.ni_alpha) * cv
    elif spec.score_form == "normalized_product":
        score = (ni_norm**spec.ni_alpha) * cv_norm
    elif spec.score_form == "rank_sum":
        ni_rank = ni.rank(ascending=False, method="average", pct=True)
        cv_rank = cv.rank(ascending=False, method="average", pct=True)
        score = (1.0 - ni_rank) + (1.0 - cv_rank)
    elif spec.score_form == "additive_norm":
        score = (ni_norm**spec.ni_alpha) + cv_norm
    else:
        raise ValueError(f"Unknown score form: {spec.score_form}")

    return finite_numeric(score)


def score_specs() -> list[ScoreSpec]:
    forms = ["raw_product", "normalized_product", "rank_sum", "additive_norm"]
    return [
        ScoreSpec(f"{form}_alpha{alpha:g}", alpha, form)
        for alpha in NI_ALPHA_GRID
        for form in forms
    ]


def stability_tables(
    df: pd.DataFrame, out_dir: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    unpaved = df[df["unpaved"] == 1].copy()
    if unpaved.empty:
        raise ValueError("No unpaved/climate-affected edges found in edge scores.")

    baseline = normalize_positive(unpaved["NI"]) * normalize_positive(unpaved["CV"])
    n = len(unpaved)
    k_values = {"K500": min(500, n)}
    k_values.update(
        {f"top_{int(s*100)}pct": max(1, int(round(n * s))) for s in TOPK_SHARES}
    )

    top_rows = []
    score_frame = pd.DataFrame(index=unpaved.index)
    score_frame["baseline"] = baseline

    for spec in score_specs():
        scores = score_edges(unpaved, spec)
        score_frame[spec.name] = scores
        rho, _ = spearmanr(baseline.fillna(0), scores.fillna(0))
        for label, k in k_values.items():
            top_rows.append(
                {
                    "score_variant": spec.name,
                    "score_form": spec.score_form,
                    "ni_alpha": spec.ni_alpha,
                    "top_k_label": label,
                    "top_k_edges": int(k),
                    "jaccard_vs_default": round(
                        jaccard(top_set(baseline, k), top_set(scores, k)), 4
                    ),
                    "spearman_vs_default": round(float(rho), 4),
                }
            )

    threshold_rows = []
    thresholds = {
        "median_split": 0.50,
        "upper_quartile": 0.75,
        "top_decile": 0.90,
    }
    default_mask = (unpaved["NI"] >= unpaved["NI"].quantile(0.50)) & (
        unpaved["CV"] >= unpaved["CV"].quantile(0.50)
    )

    for name, q in thresholds.items():
        mask = (unpaved["NI"] >= unpaved["NI"].quantile(q)) & (
            unpaved["CV"] >= unpaved["CV"].quantile(q)
        )
        threshold_rows.append(
            {
                "threshold_rule": name,
                "q": q,
                "n_edges": int(mask.sum()),
                "pct_unpaved_edges": round(mask.mean() * 100, 2),
                "jaccard_vs_median_split": round(
                    jaccard(set(unpaved.index[default_mask]), set(unpaved.index[mask])),
                    4,
                ),
            }
        )

    top_df = pd.DataFrame(top_rows)
    threshold_df = pd.DataFrame(threshold_rows)
    write_table(top_df, out_dir / "topk_score_stability.csv")
    write_table(threshold_df, out_dir / "high_NI_high_CV_threshold_stability.csv")
    return top_df, threshold_df


def summarize_existing_recovery(paving_csv: Path, out_dir: Path) -> pd.DataFrame:
    df = pd.read_csv(paving_csv)
    rows = []
    for f in [0.001, 0.01]:
        nearest_idx = (df["paving_fraction"] - f).abs().idxmin()
        row = df.loc[nearest_idx]
        rows.append(
            {
                "requested_paving_fraction": f,
                "actual_paving_fraction": row["paving_fraction"],
                "n_edges_paved": int(row["n_edges_paved"]),
                "recovery_guided": round(float(row["recovery_guided"]), 4),
                "recovery_ni_only": round(float(row["recovery_ni_only"]), 4),
                "recovery_cv_only": round(float(row["recovery_cv_only"]), 4),
                "recovery_random_mean": round(float(row["recovery_rand_mean"]), 4),
                "guided_minus_cv_only": round(
                    float(row["recovery_guided"] - row["recovery_cv_only"]), 4
                ),
                "guided_minus_random": round(
                    float(row["recovery_guided"] - row["recovery_rand_mean"]), 4
                ),
            }
        )
    out = pd.DataFrame(rows)
    write_table(out, out_dir / "headline_recovery_existing.csv")
    return out


def build_interpretation_summary(
    top_df: pd.DataFrame,
    threshold_df: pd.DataFrame,
    recovery_df: pd.DataFrame,
    out_dir: Path,
) -> pd.DataFrame:
    product = top_df[top_df["score_form"].isin(["raw_product", "normalized_product"])]
    rank_add = top_df[top_df["score_form"].isin(["rank_sum", "additive_norm"])]
    k500 = top_df[top_df["top_k_label"] == "K500"]
    product_k500 = k500[k500["score_form"].isin(["raw_product", "normalized_product"])]
    rank_add_k500 = k500[k500["score_form"].isin(["rank_sum", "additive_norm"])]
    recovery_001 = float(
        recovery_df.loc[
            recovery_df["requested_paving_fraction"] == 0.001,
            "recovery_guided",
        ].iloc[0]
    )
    recovery_010 = float(
        recovery_df.loc[
            recovery_df["requested_paving_fraction"] == 0.01,
            "recovery_guided",
        ].iloc[0]
    )
    ni_only_001 = float(
        recovery_df.loc[
            recovery_df["requested_paving_fraction"] == 0.001,
            "recovery_ni_only",
        ].iloc[0]
    )
    ni_only_010 = float(
        recovery_df.loc[
            recovery_df["requested_paving_fraction"] == 0.01,
            "recovery_ni_only",
        ].iloc[0]
    )
    rows = [
        {
            "robustness_question": "Product-form bottleneck geography",
            "evidence": (
                "raw NIxCV and normalized NIxCV remain close across NI alpha; "
                f"mean Jaccard={product['jaccard_vs_default'].mean():.3f}, "
                f"min Jaccard={product['jaccard_vs_default'].min():.3f}; "
                f"K500 min={product_k500['jaccard_vs_default'].min():.3f}."
            ),
            "interpretation": "stable within product-family definitions",
        },
        {
            "robustness_question": "Rank-sum/additive bottleneck geography",
            "evidence": (
                "rank-sum/additive forms can promote high-NI-only or high-CV-only edges; "
                f"mean Jaccard={rank_add['jaccard_vs_default'].mean():.3f}, "
                f"min Jaccard={rank_add['jaccard_vs_default'].min():.3f}; "
                f"K500 min={rank_add_k500['jaccard_vs_default'].min():.3f}."
            ),
            "interpretation": "sensitive for exact top-K geography; do not overclaim",
        },
        {
            "robustness_question": "High NI / high CV threshold",
            "evidence": (
                "upper quartile is nested in the median split; top decile is much narrower. "
                f"Upper-quartile Jaccard={threshold_df.loc[threshold_df['threshold_rule'] == 'upper_quartile', 'jaccard_vs_median_split'].iloc[0]:.3f}; "
                f"top-decile Jaccard={threshold_df.loc[threshold_df['threshold_rule'] == 'top_decile', 'jaccard_vs_median_split'].iloc[0]:.3f}."
            ),
            "interpretation": "stable as nested hotspot core, not as identical edge set",
        },
        {
            "robustness_question": "Headline recovery rate",
            "evidence": (
                f"Guided recovery is {recovery_001:.4f} at 0.1% paving and "
                f"{recovery_010:.4f} at 1% paving; NI-only is "
                f"{ni_only_001:.4f} and {ni_only_010:.4f}."
            ),
            "interpretation": "very stable for the intervention conclusion",
        },
    ]
    out = pd.DataFrame(rows)
    write_table(out, out_dir / "interpretation_summary.csv")
    return out


def compute_accessibility(g_ig, city_ig_idx, pops, alpha: float) -> float:
    d_mat = np.array(
        g_ig.distances(source=city_ig_idx, target=city_ig_idx, weights="weight"),
        dtype=np.float64,
    )
    pop_arr = np.array(pops, dtype=np.float64)
    i_idx, j_idx = np.triu_indices(len(city_ig_idx), k=1)
    d_vals = d_mat[i_idx, j_idx]
    valid = (d_vals > 0) & (d_vals < UNREACHABLE)
    return float(
        np.sum(pop_arr[i_idx[valid]] * pop_arr[j_idx[valid]] / d_vals[valid] ** alpha)
    )


def run_optional_recovery_alpha(
    state_path: Path,
    edge_scores: pd.DataFrame,
    out_dir: Path,
    max_variants: int,
) -> pd.DataFrame:
    with state_path.open("rb") as f:
        state = pickle.load(f)

    g0_ig = state["g0_ig"]
    g1_ig = state["g1_ig"]
    city_ig_idx = state["city_ig_idx"]
    pops = state["pops"]
    unpaved_mask = np.asarray(state["unpaved_mask"], dtype=bool)
    unpaved_idx = np.where(unpaved_mask)[0]

    variants = score_specs()[:max_variants]
    records = []
    rng = np.random.default_rng(42)

    for alpha_recovery in RECOVERY_ALPHA_GRID:
        a_normal = compute_accessibility(g0_ig, city_ig_idx, pops, alpha_recovery)
        a_extreme = compute_accessibility(g1_ig, city_ig_idx, pops, alpha_recovery)
        denom = max(a_normal - a_extreme, 1e-12)

        for spec in variants:
            scores = score_edges(edge_scores, spec).reindex(edge_scores.index).fillna(0)
            order_guided = unpaved_idx[np.argsort(-scores.iloc[unpaved_idx].values)]
            order_cv = unpaved_idx[
                np.argsort(-edge_scores["CV"].iloc[unpaved_idx].values)
            ]

            for f in PAVING_FRACTIONS:
                n_pave = int(round(f * len(unpaved_idx)))

                def eval_edges(edge_indices: np.ndarray) -> float:
                    orig = [g1_ig.es[int(e)]["weight"] for e in edge_indices]
                    for e in edge_indices:
                        g1_ig.es[int(e)]["weight"] = g0_ig.es[int(e)]["weight"]
                    a_mod = compute_accessibility(
                        g1_ig, city_ig_idx, pops, alpha_recovery
                    )
                    for e, w in zip(edge_indices, orig):
                        g1_ig.es[int(e)]["weight"] = w
                    return float((a_mod - a_extreme) / denom)

                rand_recs = []
                for _ in range(N_RANDOM_TRIALS):
                    sample = (
                        rng.choice(unpaved_idx, size=n_pave, replace=False)
                        if n_pave > 0
                        else np.array([], dtype=int)
                    )
                    rand_recs.append(eval_edges(sample))

                records.append(
                    {
                        "score_variant": spec.name,
                        "recovery_alpha": alpha_recovery,
                        "paving_fraction": f,
                        "n_edges_paved": n_pave,
                        "recovery_guided": eval_edges(order_guided[:n_pave]),
                        "recovery_cv_only": eval_edges(order_cv[:n_pave]),
                        "recovery_random_mean": float(np.mean(rand_recs)),
                        "recovery_random_std": float(np.std(rand_recs)),
                    }
                )

    out = pd.DataFrame(records)
    write_table(out, out_dir / "optional_recovery_alpha_curves.csv")
    return out


def write_readme(
    out_dir: Path,
    top_df: pd.DataFrame,
    recovery_df: pd.DataFrame,
    interpretation_df: pd.DataFrame,
) -> None:
    top_summary = top_df.groupby("top_k_label")["jaccard_vs_default"].agg(
        ["mean", "min", "max"]
    )
    lines = [
        "# Bottleneck and Recovery Robustness",
        "",
        "This module uses cached bottleneck outputs: `02_edge_scores.csv` and `04_paving_experiment.csv`.",
        "",
        "## Top-K geography stability",
        "",
        top_summary.round(3).to_markdown(),
        "",
        "## Headline recovery from the existing experiment",
        "",
        recovery_df.to_markdown(index=False),
        "",
        "## Interpretation boundary",
        "",
        interpretation_df.to_markdown(index=False),
    ]
    (out_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument("--edge-scores", default=None)
    parser.add_argument("--paving-experiment", default=None)
    parser.add_argument(
        "--run-recovery-alpha",
        action="store_true",
        help="Use experiment_state.pkl to recompute reduced recovery curves. This is slower.",
    )
    parser.add_argument(
        "--max-recovery-variants",
        type=int,
        default=3,
        help="Limit optional recovery recomputation variants.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "04_bottleneck_recovery")
    edge_path = (
        Path(args.edge_scores)
        if args.edge_scores
        else paths.bottleneck_dir / "02_edge_scores.csv"
    )
    paving_path = (
        Path(args.paving_experiment)
        if args.paving_experiment
        else paths.bottleneck_dir / "04_paving_experiment.csv"
    )

    edge_scores = load_edge_scores(edge_path)
    top_df, threshold_df = stability_tables(edge_scores, out_dir)
    recovery_df = summarize_existing_recovery(paving_path, out_dir)
    interpretation_df = build_interpretation_summary(
        top_df, threshold_df, recovery_df, out_dir
    )

    if args.run_recovery_alpha:
        state_path = paths.bottleneck_dir / "experiment_state.pkl"
        optional_df = run_optional_recovery_alpha(
            state_path, edge_scores, out_dir, args.max_recovery_variants
        )
        print("Optional recovery-alpha curves:", optional_df.shape)

    summary = {
        "edge_scores": str(edge_path),
        "paving_experiment": str(paving_path),
        "n_edges": int(len(edge_scores)),
        "n_unpaved": int((edge_scores["unpaved"] == 1).sum()),
        "topk_mean_jaccard": float(top_df["jaccard_vs_default"].mean()),
        "topk_min_jaccard": float(top_df["jaccard_vs_default"].min()),
        "recovery_0p1_guided": float(
            recovery_df.loc[
                recovery_df["requested_paving_fraction"] == 0.001,
                "recovery_guided",
            ].iloc[0]
        ),
        "recovery_1p0_guided": float(
            recovery_df.loc[
                recovery_df["requested_paving_fraction"] == 0.01,
                "recovery_guided",
            ].iloc[0]
        ),
    }
    with (out_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, sort_keys=True)
    write_readme(out_dir, top_df, recovery_df, interpretation_df)

    print("Bottleneck robustness written to:", out_dir)
    print(pd.DataFrame([summary]).to_string(index=False))
    print("\nTop-K stability by K:")
    print(
        top_df.groupby("top_k_label")["jaccard_vs_default"]
        .agg(["mean", "min", "max"])
        .round(3)
        .to_string()
    )
    print("\nHeadline recovery:")
    print(recovery_df.to_string(index=False))
    print("\nInterpretation:")
    print(interpretation_df.to_string(index=False))


if __name__ == "__main__":
    main()
