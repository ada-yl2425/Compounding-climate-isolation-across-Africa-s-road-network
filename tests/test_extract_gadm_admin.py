"""Tiny synthetic gates for GADM finest-polygons -> L2/L1 conversion."""

import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("shapely", minversion="2.0")
from shapely.geometry import box

from hpc.extract_gadm_admin import aggregate_country, extract


def _source(gid2=("KEN.1.1_1", "KEN.1.1_1", "KEN.1.2_1"), *, overlap=False):
    geometries = [box(0, 0, 1, 1), box(1, 0, 2, 1), box(2, 0, 3, 1)]
    if overlap:
        geometries[1] = box(0.5, 0, 1.5, 1)
    return gpd.GeoDataFrame(
        {
            "GID_0": ["KEN"] * 3,
            "GID_1": ["KEN.1_1"] * 3,
            "GID_2": list(gid2),
            "NAME_0": ["Kenya"] * 3,
            "NAME_1": ["County"] * 3,
            "NAME_2": ["A", "A", "B"] if gid2[0] else ["", "", ""],
            "GID_3": ["KEN.1.1.1_1", "KEN.1.1.2_1", "KEN.1.2.1_1"],
        },
        geometry=geometries,
        crs="EPSG:4326",
    )


def test_dissolves_deepest_polygons_to_unique_l2():
    output, qc = aggregate_country(_source(), "KEN")
    assert qc["status"] == "PASS"
    assert qc["admin_level"] == 2
    assert qc["source_rows"] == 3
    assert qc["target_unique_admin_gid"] == 2
    assert output.set_index("admin_gid").loc["KEN.1.1_1", "source_rows"] == 2
    assert qc["symmetric_difference_km2"] < 1e-6
    assert output.crs.to_epsg() == 4326


def test_all_missing_l2_falls_back_to_l1():
    output, qc = aggregate_country(_source(("", "", "")), "KEN")
    assert qc["status"] == "PASS"
    assert qc["admin_level"] == 1
    assert qc["target_unique_admin_gid"] == 1
    assert output.iloc[0]["admin_gid"] == "KEN.1_1"


def test_mixed_l2_does_not_silently_drop_area():
    with pytest.raises(ValueError, match="mixed empty/nonempty GID_2"):
        aggregate_country(_source(("KEN.1.1_1", "", "KEN.1.2_1")), "KEN")


def test_overlap_fails_qc_even_when_union_matches():
    _output, qc = aggregate_country(_source(overlap=True), "KEN")
    assert qc["status"] == "FAIL"
    assert qc["source_overlap_km2"] > qc["area_tolerance_km2"]


def test_country_filter_and_gpkg_output(tmp_path):
    pytest.importorskip("fiona")
    source = _source()
    source.loc[3] = [
        "UGA",
        "UGA.1_1",
        "UGA.1.1_1",
        "Uganda",
        "Other",
        "Other",
        "UGA.1.1.1_1",
        box(5, 0, 6, 1),
    ]
    source = gpd.GeoDataFrame(source, geometry="geometry", crs="EPSG:4326")
    input_path = tmp_path / "global.gpkg"
    output_path = tmp_path / "ken_l2.gpkg"
    report_path = tmp_path / "ken_qc.json"
    source.to_file(input_path, layer="gadm_410", driver="GPKG", index=False)
    qc = extract(input_path, output_path, report_path, "KEN")
    assert qc["status"] == "PASS"
    assert qc["source_rows"] == 3
    assert output_path.exists() and report_path.exists()
    reread = gpd.read_file(output_path, layer="gadm41_KEN_2")
    assert len(reread) == 2
    assert set(reread["GID_0"]) == {"KEN"}
