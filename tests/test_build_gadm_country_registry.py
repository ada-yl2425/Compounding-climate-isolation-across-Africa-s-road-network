"""Input-free checks for the 49-country GADM array registry."""

import sqlite3
from pathlib import Path

import pytest

from hpc.build_gadm_country_registry import (
    code_country_mapping,
    formal_mapping,
    make_registry,
    source_gid_counts,
)


def test_code_mapping_is_49_formal_countries_without_esh():
    mapping = code_country_mapping(Path("data_procession/prepare_city_layer.py"))
    formal = formal_mapping(mapping)
    assert len(mapping) == 50
    assert len(formal) == 49
    assert "ESH" not in formal.values()
    assert formal["Kenya"] == "KEN"


def _tiny_connection():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE gadm_410(GID_0 TEXT,GID_1 TEXT,GID_2 TEXT,geom BLOB)"
    )
    connection.executemany(
        "INSERT INTO gadm_410 VALUES(?,?,?,?)",
        [
            ("KEN", "KEN.1_1", "KEN.1.1_1", b"x"),
            ("KEN", "KEN.1_1", "KEN.1.1_1", b"x"),
            ("KEN", "KEN.1_1", "KEN.1.2_1", b"x"),
            ("LSO", "LSO.1_1", "", b"x"),
            ("LSO", "LSO.1_1", "", b"x"),
            ("ESH", "ESH.1_1", "", b"x"),
        ],
    )
    return connection


def test_sqlite_counts_and_l1_fallback():
    conn = _tiny_connection()
    counts = source_gid_counts(conn, ["KEN", "LSO"], layer="gadm_410")
    assert counts["KEN"]["source_rows"] == 3
    assert counts["KEN"]["unique_gid2"] == 2
    assert counts["LSO"]["empty_gid2_rows"] == 2
    formal = {"Kenya": "KEN", "Lesotho": "LSO"}
    rows = make_registry(formal, counts)
    assert [
        (row["iso3"], row["admin_level"], row["target_unique_gid"]) for row in rows
    ] == [
        ("KEN", 2, 2),
        ("LSO", 1, 1),
    ]
    assert [row["array_index"] for row in rows] == [1, 2]


def test_missing_iso_and_mixed_l2_are_rejected():
    conn = _tiny_connection()
    counts = source_gid_counts(conn, ["KEN", "LSO"], layer="gadm_410")
    with pytest.raises(ValueError, match="missing formal ISO3"):
        make_registry({"Kenya": "KEN", "Uganda": "UGA"}, counts)
    counts["KEN"]["empty_gid2_rows"] = 1
    with pytest.raises(ValueError, match="mixed empty/nonempty GID_2"):
        make_registry({"Kenya": "KEN"}, counts)


def test_pbs_array_has_registry_gate_and_no_auto_submit():
    source = Path("hpc/pbs_gadm_admin_array.pbs").read_text(encoding="utf-8")
    assert "#PBS -J 1-49" in source
    assert "registry_sha256" in source
    assert "hpc.extract_gadm_admin" in source
    assert "qsub " not in source
