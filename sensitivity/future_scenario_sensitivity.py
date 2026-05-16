"""Summarize future-scenario bottleneck stability and missing high-forcing inputs."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

from sensitivity.config import add_common_path_args, resolve_paths
from sensitivity.io_utils import ensure_dir, write_table


RAW_CLIMATE_RE = re.compile(
    r"^(?P<var>pr|mrso)_AFR-44_(?P<gcm>.+?)_(?P<rcp>rcp\d+)_"
    r".*?_(?P<freq>mon|day)_(?P<start>\d{6,8})-(?P<end>\d{6,8})\.nc$"
)


def scenario_parts(name: str) -> dict:
    parts = name.split("_")
    period = parts[-1] if parts else ""
    rcp = next((p for p in parts if p.startswith("rcp")), "")
    gcm = name[: -len(f"_{rcp}_{period}")] if rcp and period else name
    return {"scenario_dir": name, "gcm": gcm, "rcp": rcp, "period": period}


def parse_raw_climate_file(path: Path, base: Path) -> dict | None:
    match = RAW_CLIMATE_RE.match(path.name)
    if not match:
        return None
    row = match.groupdict()
    row["relative_path"] = str(path.relative_to(base))
    row["start_year"] = int(row["start"][:4])
    row["end_year"] = int(row["end"][:4])
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_common_path_args(parser)
    parser.add_argument("--required-rcps", nargs="*", default=["rcp45", "rcp85"])
    parser.add_argument(
        "--scan-edge-files",
        action="store_true",
        help="Also summarize large bottleneck_stability_<rcp>_<period>.csv files.",
    )
    args = parser.parse_args()

    paths = resolve_paths(args.base_dir, args.output_dir)
    out_dir = ensure_dir(paths.output_root / "05_future_scenarios")

    raw_rows = []
    for nc_path in sorted(paths.climate_data.rglob("*.nc")):
        row = parse_raw_climate_file(nc_path, paths.data_base)
        if row:
            raw_rows.append(row)
    raw_inventory = pd.DataFrame(raw_rows)
    if not raw_inventory.empty:
        write_table(raw_inventory, out_dir / "raw_climate_rcp_inventory.csv")

        coverage_rows = []
        for rcp in args.required_rcps:
            subset = raw_inventory[raw_inventory["rcp"] == rcp]
            for gcm in sorted(subset["gcm"].unique()):
                gcm_subset = subset[subset["gcm"] == gcm]
                for period in [2045, 2065, 2085]:
                    start_year, end_year = period - 5, period + 5
                    row = {"rcp": rcp, "gcm": gcm, "period": period}
                    for var in ["pr", "mrso"]:
                        var_subset = gcm_subset[gcm_subset["var"] == var]
                        covers = var_subset[
                            (var_subset["start_year"] <= end_year)
                            & (var_subset["end_year"] >= start_year)
                        ]
                        row[f"has_{var}"] = not covers.empty
                        row[f"n_{var}_files"] = int(len(covers))
                    row["window_status"] = (
                        "ready" if row["has_pr"] and row["has_mrso"] else "missing"
                    )
                    coverage_rows.append(row)
        write_table(
            pd.DataFrame(coverage_rows),
            out_dir / "raw_climate_window_coverage.csv",
        )

    inventory_rows = []
    for scenario_dir in sorted(paths.road_speed_future.glob("*")):
        if not scenario_dir.is_dir():
            continue
        row = scenario_parts(scenario_dir.name)
        row["n_country_speed_csv"] = len(list(scenario_dir.glob("*_road_speed.csv")))
        inventory_rows.append(row)
    inventory = pd.DataFrame(inventory_rows)
    write_table(inventory, out_dir / "future_speed_inventory.csv")

    report_path = paths.bottleneck_dir / "bottleneck_stability_report.csv"
    report = pd.DataFrame()
    if report_path.exists():
        report = pd.read_csv(report_path)
        write_table(report, out_dir / "cached_bottleneck_stability_report.csv")

    robustness_report_rows = []
    for path in sorted(out_dir.glob("*stability_summary*.csv")):
        try:
            df = pd.read_csv(path)
        except Exception:
            continue
        if {"gcm", "rcp", "period"}.issubset(df.columns):
            df = df.copy()
            df["source_file"] = path.name
            robustness_report_rows.append(df)
    robustness_report = (
        pd.concat(robustness_report_rows, ignore_index=True)
        if robustness_report_rows
        else pd.DataFrame()
    )
    if not robustness_report.empty:
        write_table(
            robustness_report,
            out_dir / "robustness_future_stability_report.csv",
        )

    stability_rows = []
    if args.scan_edge_files:
        stability_files = sorted(paths.bottleneck_dir.glob("bottleneck_stability*.csv"))
        for path in stability_files:
            if path.name == "bottleneck_stability_report.csv" or "report" in path.name:
                continue
            df = pd.read_csv(path, usecols=lambda c: c in {"CV_future", "bottleneck_future"})
            if df.empty:
                continue
            parts = path.stem.replace("bottleneck_stability_", "").split("_")
            rcp = parts[0] if parts else ""
            period = parts[1] if len(parts) > 1 else ""
            stability_rows.append(
                {
                    "file": path.name,
                    "rcp": rcp,
                    "period": period,
                    "n_edges": int(len(df)),
                    "mean_cv_future": round(float(df["CV_future"].mean()), 4)
                    if "CV_future" in df.columns
                    else None,
                    "mean_bottleneck_future": round(
                        float(df["bottleneck_future"].mean()), 6
                    )
                    if "bottleneck_future" in df.columns
                    else None,
                }
            )
    stability = pd.DataFrame(stability_rows)
    if not stability.empty:
        write_table(stability, out_dir / "future_stability_file_summary.csv")

    required_rows = []
    for rcp in args.required_rcps:
        has_speed = False if inventory.empty else bool((inventory["rcp"] == rcp).any())
        has_edge_stability = False if stability.empty else bool((stability["rcp"] == rcp).any())
        has_report_stability = (
            False
            if report.empty or "rcp" not in report.columns or "status" not in report.columns
            else bool(((report["rcp"] == rcp) & (report["status"] == "ok")).any())
        )
        has_robustness_stability = (
            False
            if robustness_report.empty or "rcp" not in robustness_report.columns
            else bool((robustness_report["rcp"] == rcp).any())
        )
        has_stability = (
            has_edge_stability or has_report_stability or has_robustness_stability
        )
        required_rows.append(
            {
                "rcp": rcp,
                "has_future_speed_dir": has_speed,
                "has_bottleneck_stability_output": has_stability,
                "status": "ready" if has_speed and has_stability else "missing_inputs",
            }
        )
    required = pd.DataFrame(required_rows)
    write_table(required, out_dir / "required_future_scenario_status.csv")

    print("Future scenario robustness inventory written to:", out_dir)
    print(required.to_string(index=False))


if __name__ == "__main__":
    main()
