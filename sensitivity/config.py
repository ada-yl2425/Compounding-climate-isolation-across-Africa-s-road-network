"""Shared paths and scenario grids for robustness scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DATA_BASE = Path(
    os.environ.get(
        "AFRICA_PAVEMENT_BASE",
        "path/to/africa_pavement",
    )
)
DEFAULT_OUTPUT_NAME = "sensitivity"

COUNTRIES = [
    "Algeria",
    "Angola",
    "Benin",
    "Botswana",
    "BurkinaFaso",
    "Burundi",
    "Cameroon",
    "CentralAfrican",
    "Chad",
    "Congo",
    "CongoDR",
    "Djibouti",
    "Egypt",
    "Equatorial",
    "Eritrea",
    "Ethiopia",
    "Gabon",
    "Gambia",
    "Ghana",
    "Guinea",
    "GuineaBissau",
    "IvoryCoast",
    "Kenya",
    "Lesotho",
    "Liberia",
    "Libya",
    "Madagascar",
    "Malawi",
    "Mali",
    "Mauritania",
    "Morocco",
    "Mozambique",
    "Namibia",
    "Niger",
    "Nigeria",
    "Rwanda",
    "Senegal",
    "SierraLeone",
    "Somalia",
    "SouthAfrica",
    "SouthSudan",
    "Sudan",
    "Swaziland",
    "Tanzania",
    "Togo",
    "Tunisia",
    "Uganda",
    "WestSahara",
    "Zambia",
    "Zimbabwe",
]

WORLDPOP_PREFIX = {
    "Algeria": "dza",
    "Angola": "ago",
    "Benin": "ben",
    "Botswana": "bwa",
    "BurkinaFaso": "bfa",
    "Burundi": "bdi",
    "Cameroon": "cmr",
    "CentralAfrican": "caf",
    "Chad": "tcd",
    "Congo": "cog",
    "CongoDR": "cod",
    "Djibouti": "dji",
    "Egypt": "egy",
    "Equatorial": "gnq",
    "Eritrea": "eri",
    "Ethiopia": "eth",
    "Gabon": "gab",
    "Gambia": "gmb",
    "Ghana": "gha",
    "Guinea": "gin",
    "GuineaBissau": "gnb",
    "IvoryCoast": "civ",
    "Kenya": "ken",
    "Lesotho": "lso",
    "Liberia": "lbr",
    "Libya": "lby",
    "Madagascar": "mdg",
    "Malawi": "mwi",
    "Mali": "mli",
    "Mauritania": "mrt",
    "Morocco": "mar",
    "Mozambique": "moz",
    "Namibia": "nam",
    "Niger": "ner",
    "Nigeria": "nga",
    "Rwanda": "rwa",
    "Senegal": "sen",
    "SierraLeone": "sle",
    "Somalia": "som",
    "SouthAfrica": "zaf",
    "SouthSudan": "ssd",
    "Sudan": "sdn",
    "Swaziland": "swz",
    "Tanzania": "tza",
    "Togo": "tgo",
    "Tunisia": "tun",
    "Uganda": "uga",
    "WestSahara": "",
    "Zambia": "zmb",
    "Zimbabwe": "zwe",
}

PRECIP_PERCENTILES = [90.0, 95.0, 97.5, 99.0]
SOIL_MOISTURE_THRESHOLDS = [70.0, 75.0, 80.0]
HEALTH_SNAP_KM = [25.0, 50.0, 100.0]
NI_ALPHA_GRID = [1.5, 2.0, 2.5]
RECOVERY_ALPHA_GRID = [1.0, 2.0]
TOPK_SHARES = [0.01, 0.03, 0.05, 0.10]


@dataclass(frozen=True)
class Paths:
    data_base: Path
    output_root: Path
    road_speed: Path
    road_speed_future: Path
    road_data: Path
    health_data: Path
    pop_data: Path
    climate_data: Path
    network_results: Path
    health_accessibility: Path
    bottleneck_dir: Path


def resolve_paths(
    base_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> Paths:
    data_base = Path(base_dir) if base_dir else DEFAULT_DATA_BASE
    output_root = Path(output_dir) if output_dir else data_base / DEFAULT_OUTPUT_NAME
    return Paths(
        data_base=data_base,
        output_root=output_root,
        road_speed=data_base / "road_speed_cordex",
        road_speed_future=data_base / "road_speed_future",
        road_data=data_base / "RAW" / "Road_data",
        health_data=data_base / "RAW" / "Health_data",
        pop_data=data_base / "RAW" / "Pop_data",
        climate_data=data_base / "RAW" / "Climate_data",
        network_results=data_base / "web" / "network_results",
        health_accessibility=data_base / "web" / "health_accessibility",
        bottleneck_dir=data_base / "web" / "network_results" / "bottleneck_paving",
    )


def add_common_path_args(parser) -> None:
    parser.add_argument(
        "--base-dir",
        default=str(DEFAULT_DATA_BASE),
        help="Data base directory.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=f"Output directory. Default: <base-dir>/{DEFAULT_OUTPUT_NAME}",
    )
