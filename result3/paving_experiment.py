"""
paving_experiment.py  —  Step 8: Paving Simulation

Loads the serialised network state produced by data_procession/bottleneck_network.py
and runs the four-strategy paving experiment.

Usage:
    python result3/paving_experiment.py --base <BASE_DIR>

Input:
    <BASE_DIR>/web/network_results/bottleneck_paving/experiment_state.pkl

Output:
    <BASE_DIR>/web/network_results/bottleneck_paving/04_paving_experiment.csv
"""

import argparse
import pickle
from pathlib import Path

import numpy as np
import pandas as pd

# ── Simulation parameters ─────────────────────────────────────────────────────
PAVING_FRACTIONS = [
    0.000,
    0.001,
    0.002,
    0.005,
    0.010,
    0.020,
    0.030,
    0.050,
    0.075,
    0.100,
    0.150,
    0.200,
    0.300,
    0.400,
    0.500,
]
N_RANDOM_TRIALS = 5
UNREACHABLE = 1e8


def compute_accessibility(g_ig, city_ig_idx, pops, alpha=1.0):
    """Gravity-weighted inter-city accessibility index."""
    d_mat = np.array(
        g_ig.distances(source=city_ig_idx, target=city_ig_idx, weights="weight"),
        dtype=np.float64,
    )
    pop_arr = np.array(pops, dtype=np.float64)
    i_idx, j_idx = np.triu_indices(len(city_ig_idx), k=1)
    d_vals = d_mat[i_idx, j_idx]
    valid = (d_vals > 0) & (d_vals < UNREACHABLE)
    A = float(
        np.sum(pop_arr[i_idx[valid]] * pop_arr[j_idx[valid]] / d_vals[valid] ** alpha)
    )
    return A, int(valid.sum())


def run_paving_experiment(state: dict, out_dir: Path) -> pd.DataFrame:
    print(f"\n{'='*60}\n  STEP 8 — Paving Simulation (4 strategies)\n{'='*60}")

    g0_ig = state["g0_ig"]
    g1_ig = state["g1_ig"]
    city_ig_idx = state["city_ig_idx"]
    pops = state["pops"]
    A_normal = state["A_normal"]
    A_extreme = state["A_extreme"]
    gbc = state["gbc"]
    cv_arr = state["cv_arr"]
    bottleneck = state["bottleneck"]
    unpaved_mask = state["unpaved_mask"]

    unpaved_idx = np.where(unpaved_mask)[0]
    n_unpaved = len(unpaved_idx)
    print(f"  Unpaved edge pool: {n_unpaved:,}")

    order_guided = unpaved_idx[np.argsort(-bottleneck[unpaved_idx])]
    order_ni_only = unpaved_idx[np.argsort(-gbc[unpaved_idx])]
    order_cv_only = unpaved_idx[np.argsort(-cv_arr[unpaved_idx])]

    def pave_and_eval(edge_indices):
        orig_w = [g1_ig.es[e]["weight"] for e in edge_indices]
        for e in edge_indices:
            g1_ig.es[e]["weight"] = g0_ig.es[e]["weight"]
        A, _ = compute_accessibility(g1_ig, city_ig_idx, pops)
        for e, w in zip(edge_indices, orig_w):
            g1_ig.es[e]["weight"] = w
        return A

    def recovery(A_mod):
        denom = A_normal - A_extreme
        return float((A_mod - A_extreme) / denom) if denom > 1e-12 else 0.0

    rng = np.random.default_rng(42)
    records = []

    for f in PAVING_FRACTIONS:
        n_pave = int(round(f * n_unpaved))
        rec = {
            "paving_fraction": f,
            "n_edges_paved": n_pave,
            "A_normal": A_normal,
            "A_extreme": A_extreme,
        }

        A_guided = pave_and_eval(order_guided[:n_pave])
        rec["A_guided"] = A_guided
        rec["recovery_guided"] = recovery(A_guided)

        A_ni = pave_and_eval(order_ni_only[:n_pave])
        rec["A_ni_only"] = A_ni
        rec["recovery_ni_only"] = recovery(A_ni)

        A_cv = pave_and_eval(order_cv_only[:n_pave])
        rec["A_cv_only"] = A_cv
        rec["recovery_cv_only"] = recovery(A_cv)

        rand_recoveries = []
        for _ in range(N_RANDOM_TRIALS):
            sel = rng.choice(unpaved_idx, size=n_pave, replace=False)
            rand_recoveries.append(recovery(pave_and_eval(sel)))
        rec["recovery_rand_mean"] = float(np.mean(rand_recoveries))
        rec["recovery_rand_std"] = float(np.std(rand_recoveries))

        print(
            f"  f={f:.3f}  n={n_pave:6,}  "
            f"guided={rec['recovery_guided']:.3f}  "
            f"NI={rec['recovery_ni_only']:.3f}  "
            f"CV={rec['recovery_cv_only']:.3f}  "
            f"rand={rec['recovery_rand_mean']:.3f}±{rec['recovery_rand_std']:.3f}"
        )
        records.append(rec)

    df_exp = pd.DataFrame(records)
    df_exp.to_csv(out_dir / "04_paving_experiment.csv", index=False)
    print(f"\n  Saved → 04_paving_experiment.csv")
    return df_exp


def main():
    parser = argparse.ArgumentParser(
        description="Bottleneck Paving Experiment (Step 8)"
    )
    parser.add_argument(
        "--base", required=True, help="Base directory (africa_pavement)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if 04_paving_experiment.csv already exists",
    )
    args = parser.parse_args()

    out_dir = Path(args.base) / "web" / "network_results" / "bottleneck_paving"
    csv_path = out_dir / "04_paving_experiment.csv"
    state_path = out_dir / "experiment_state.pkl"

    if csv_path.exists() and not args.force:
        print(f"  [SKIP] {csv_path.name} already exists. Use --force to re-run.")
        return

    if not state_path.exists():
        raise FileNotFoundError(
            f"{state_path} not found.\n"
            "Run data_procession/bottleneck_network.py first to generate "
            "experiment_state.pkl."
        )

    print(f"  Loading experiment state from {state_path.name} …")
    with open(state_path, "rb") as f:
        state = pickle.load(f)

    run_paving_experiment(state, out_dir)


if __name__ == "__main__":
    main()
