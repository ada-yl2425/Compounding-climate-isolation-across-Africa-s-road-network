"""Small deterministic checks for the read-only C01 input auditors."""

import zipfile

import numpy as np
import pytest

from hpc.audit_climate_input_gate import SCENARIOS, expected_files
from hpc.audit_legacy_speed_terrain import old_iri, selected_old_rows


def test_paper_climate_registry_has_exact_eight_pairs_and_sixteen_files():
    files = list(expected_files())
    assert len(SCENARIOS) == 8
    assert len(files) == 16
    assert len({item[0] for item in files}) == 16
    assert sum(item[-1] == "baseline" for item in files) == 2
    assert sum(item[-1] == "future" for item in files) == 12
    assert sum(item[-1] == "si_s8" for item in files) == 2
    assert {(item[4], item[5]) for item in files if item[-1] == "future"} == {
        (2041, 2050),
        (2061, 2070),
        (2081, 2090),
    }


def test_old_iri_zero_terrain_uses_twelve_steps_of_one_twelfth():
    monthly_precip_m = 0.13
    rate = 0.461 + 0.0174 * 42 + 0.0114 * 8 - 0.0287 * 50 * monthly_precip_m
    expected = 21.4 - np.exp(-0.001 * rate) * (21.4 - 6.0)
    assert old_iri(monthly_precip_m) == pytest.approx(expected)


def test_old_speed_zip_sampling_is_deterministic(tmp_path):
    path = tmp_path / "speed.zip"
    csv_text = "road_id,center_lat,center_lon,IRI_normal,IRI_extreme\n"
    csv_text += "".join(f"Benin_road_{i},0,0,6,6\n" for i in range(15))
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("road_speed_cordex/Benin_road_speed.csv", csv_text)
    rows = selected_old_rows(path, "Benin", stride=3)
    assert [row["road_id"] for row in rows] == [
        *(f"Benin_road_{i}" for i in range(10)),
        "Benin_road_12",
    ]
