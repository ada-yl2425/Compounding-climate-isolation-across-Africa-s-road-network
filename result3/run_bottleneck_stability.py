"""
run_bottleneck_stability.py
============================
Orchestrates the full bottleneck stability pipeline:

  Step 1 — Generate future road speed CSVs for each (GCM, RCP, period).
  Step 2 — Run bottleneck_stability.py to compare rankings and produce a
            stability report.

The 9 combinations (3 RCPs × 3 periods) cover:
  Scenarios : rcp26 (low), rcp45 (medium), rcp85 (high)
  Periods   : 2040 (near), 2060 (mid), 2080 (far)

Usage:
    python result3/run_bottleneck_stability.py \\
        --base-dir <BASE_DIR> \\
        --gcm MPI-M-MPI-ESM-LR \\
        [--climate-dir <CLIMATE_DIR>]  (override NC file location)
        [--skip-speed-gen]  (skip Step 1 if CSVs already exist)
        [--top-k 500]

Pre-requisite: NC climate files accessible in --climate-dir
    (default: {base}/RAW/Climate_data/weather_data_raw/)
    for the chosen GCM and all three RCPs.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FUTURE_SPEED_SCRIPT = REPO_ROOT / "data_procession" / "future_road_speed.py"
STABILITY_SCRIPT = Path(__file__).parent / "bottleneck_stability.py"

SCENARIOS = ["rcp26", "rcp45", "rcp85"]
PERIODS = [2045, 2065, 2085]


def run(cmd: list, label: str) -> int:
    print(f"\n{'─'*60}\n  {label}\n  CMD: {' '.join(str(c) for c in cmd)}\n{'─'*60}")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"  [ERROR] Exit code {result.returncode}")
    return result.returncode


def preflight_check(base: Path, gcm: str) -> dict:
    """Check which (rcp, period) combinations already have road speed CSVs."""
    future_base = base / "road_speed_future"
    available = {}
    for rcp in SCENARIOS:
        for period in PERIODS:
            label = f"{gcm}_{rcp}_{period}"
            d = future_base / label
            n_csv = len(list(d.glob("*_road_speed.csv"))) if d.exists() else 0
            available[(rcp, period)] = n_csv
            status = f"{n_csv:>3} CSVs" if n_csv else "missing"
            print(f"  {label:<40} {status}")
    return available


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dir", required=True)
    parser.add_argument("--gcm", default="MPI-M-MPI-ESM-LR")
    parser.add_argument(
        "--climate-dir",
        default=None,
        help="Directory containing NC climate files (overrides default path)",
    )
    parser.add_argument(
        "--skip-speed-gen",
        action="store_true",
        help="Skip Step 1 (future_road_speed.py) if CSVs already exist",
    )
    parser.add_argument("--top-k", type=int, default=500)
    parser.add_argument(
        "--window",
        type=int,
        default=4,
        help="Year window ± period for future_road_speed.py",
    )
    args = parser.parse_args()

    base = Path(args.base_dir)

    print(f"\n{'='*60}")
    print(f"  Bottleneck Stability — Full Pipeline")
    print(f"  Base dir   : {base}")
    print(f"  GCM        : {args.gcm}")
    print(f"  Scenarios  : {SCENARIOS}")
    print(f"  Periods    : {PERIODS}")
    print(f"  Climate dir: {args.climate_dir or '(default)'}")
    print(f"{'='*60}\n")

    print("[Pre-flight] Existing future road speed CSVs:")
    available = preflight_check(base, args.gcm)

    edge_scores = (
        base / "web" / "network_results" / "bottleneck_paving" / "02_edge_scores.csv"
    )
    if not edge_scores.exists():
        print(f"\n[ERROR] Edge scores not found: {edge_scores}")
        print(
            "  Run data_procession/bottleneck_network.py first to generate "
            "02_edge_scores.csv"
        )
        sys.exit(1)

    if not args.skip_speed_gen:
        print(f"\n[Step 1] Generating future road speed CSVs...")
        for rcp in SCENARIOS:
            for period in PERIODS:
                n_existing = available.get((rcp, period), 0)
                if n_existing >= 10:
                    print(
                        f"  SKIP {args.gcm}_{rcp}_{period}: {n_existing} CSVs already exist"
                    )
                    continue
                cmd = [
                    sys.executable,
                    str(FUTURE_SPEED_SCRIPT),
                    "--base-dir",
                    str(base),
                    "--gcm",
                    args.gcm,
                    "--rcp",
                    rcp,
                    "--period",
                    str(period),
                    "--window",
                    str(args.window),
                ]
                if args.climate_dir:
                    cmd += ["--climate-dir", args.climate_dir]
                rc = run(cmd, f"future_road_speed: {args.gcm} {rcp} {period}")
                if rc != 0:
                    print(f"  [WARN] Step 1 failed for {rcp} {period}, continuing...")
    else:
        print("\n[Step 1] Skipped (--skip-speed-gen set)")

    print(f"\n[Step 2] Running bottleneck stability analysis...")
    rc = run(
        [
            sys.executable,
            str(STABILITY_SCRIPT),
            "--base-dir",
            str(base),
            "--gcm",
            args.gcm,
            "--scenarios",
        ]
        + SCENARIOS
        + ["--periods"]
        + [str(p) for p in PERIODS]
        + ["--top-k", str(args.top_k)],
        "bottleneck_stability",
    )

    if rc == 0:
        report = (
            base
            / "web"
            / "network_results"
            / "bottleneck_paving"
            / "bottleneck_stability_report.csv"
        )
        print(f"\n{'='*60}")
        print(f"  Pipeline complete.")
        print(f"  Results: {report}")
        print(f"{'='*60}")
    else:
        print(f"\n[ERROR] Step 2 failed with exit code {rc}")
        sys.exit(rc)


if __name__ == "__main__":
    main()
