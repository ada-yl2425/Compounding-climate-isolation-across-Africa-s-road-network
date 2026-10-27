"""Tiny, input-free reviewer-recalculation gates.

These tests expose implementation behaviour; xfail marks known defects, not an
approved scientific specification.  No paper result may be inferred from them.
"""

import networkx as nx
import numpy as np
import pandas as pd
import pytest


def _import_speed_for_non_geospatial_test(monkeypatch, future=False):
    """Let flux/IRI tests run locally when optional GIS I/O is not installed."""
    import importlib
    import importlib.util
    import sys
    import types

    if importlib.util.find_spec("geopandas") is None:
        monkeypatch.setitem(sys.modules, "geopandas", types.ModuleType("geopandas"))
    name = "future_road_speed" if future else "compute_road_speed"
    return importlib.import_module(f"data_procession.{name}")


@pytest.mark.parametrize("future", [False, True])
def test_user_selected_iri_step_remains_one_twelfth_year(monkeypatch, future):
    """Guard the chosen submitted implementation, not its external calibration."""
    speed = _import_speed_for_non_geospatial_test(monkeypatch, future=future)
    assert speed.HDM4_DT == pytest.approx(1 / 12)


@pytest.mark.parametrize(
    ("period", "first", "last"),
    [(2045, 2041, 2050), (2065, 2061, 2070), (2085, 2081, 2090)],
)
def test_paper_future_periods_have_ten_complete_years(monkeypatch, period, first, last):
    import xarray as xr

    speed = _import_speed_for_non_geospatial_test(monkeypatch, future=True)
    years = speed.select_future_years(period)
    assert years == list(range(first, last + 1))
    months = pd.date_range(f"{first}-01-01", f"{last}-12-01", freq="MS")
    assert len(months) == 120
    climate = xr.DataArray(np.ones(len(months)), dims="time", coords={"time": months})
    speed.validate_monthly_coverage(climate, years, "synthetic")
    with pytest.raises(ValueError, match="monthly coverage mismatch"):
        speed.validate_monthly_coverage(
            climate.isel(time=slice(1, None)), years, "synthetic"
        )


def test_legacy_symmetric_future_window_requires_explicit_request(monkeypatch):
    speed = _import_speed_for_non_geospatial_test(monkeypatch, future=True)
    assert speed.select_future_years(2045, legacy_window=5) == list(range(2040, 2051))
    assert speed.select_future_years(2045, legacy_window=4) == list(range(2041, 2050))
    with pytest.raises(ValueError, match="explicit years"):
        speed.select_future_years(2045, start_year=2041, end_year=2050, legacy_window=5)
    with pytest.raises(ValueError, match="non-paper"):
        speed.select_future_years(2040)


@pytest.mark.parametrize(
    ("mmp_m", "slope_pct", "expected_target"),
    [(0.1, 13.0, 12.0), (0.0, 0.0, 21.4)],
)
def test_iri_twelve_is_a_floor_on_equilibrium_target_only(
    monkeypatch, mmp_m, slope_pct, expected_target
):
    """Check the implemented max boundary, without endorsing its units/time step."""
    pytest.importorskip("xarray")
    speed = _import_speed_for_non_geospatial_test(monkeypatch)

    monkeypatch.setattr(speed, "HDM4_MGD", 0.5)
    iri = speed.hdm4_unpaved_iri(mmp_m, kcv=0.0, slope_pct=slope_pct)
    p = np.exp(
        -0.001
        * (
            0.461
            + 0.0174 * speed.HDM4_ADL_U
            + 0.0114 * speed.HDM4_ADH_U
            - 0.0287 * speed.HDM4_ADT_U * mmp_m
        )
        * speed.HDM4_DT
    )
    expected_iri_after_12_steps = expected_target - p**12 * (
        expected_target - speed.HDM4_IRI_INIT
    )
    assert iri == pytest.approx(expected_iri_after_12_steps)
    if expected_target == 12.0:
        assert iri < 12.0  # 12 is not an instantaneous floor on IRI state.


@pytest.mark.parametrize("loader", ["baseline", "future"])
@pytest.mark.parametrize("use_bounds", [False, True])
def test_monthly_precipitation_uses_actual_28_and_31_day_months(
    monkeypatch, tmp_path, loader, use_bounds
):
    import xarray as xr

    dates = pd.to_datetime(["2021-02-01", "2021-03-01"])
    pr = xr.DataArray(
        np.ones((2, 1, 1)),
        dims=("time", "rlat", "rlon"),
        coords={"time": dates, "rlat": [0], "rlon": [0]},
        attrs={"units": "kg m-2 s-1"},
    )
    ds = xr.Dataset({"pr": pr})
    if use_bounds:
        ds["time_bnds"] = (
            ("time", "bnds"),
            np.array(
                [
                    ["2021-02-01", "2021-03-01"],
                    ["2021-03-01", "2021-04-01"],
                ],
                dtype="datetime64[ns]",
            ),
        )
        ds.time.attrs["bounds"] = "time_bnds"

    if loader == "baseline":
        speed = _import_speed_for_non_geospatial_test(monkeypatch)

        monkeypatch.setattr(speed, "find_nc_files", lambda *args: ["synthetic.nc"])
        monkeypatch.setattr(speed.xr, "open_mfdataset", lambda *args, **kwargs: ds)
        monthly_mm = speed.load_monthly_pr("GCM", "rcp45", "RCM", [2021])
    else:
        speed = _import_speed_for_non_geospatial_test(monkeypatch, future=True)

        monkeypatch.setattr(
            speed, "_find_nc_files", lambda *args: [tmp_path / "synthetic.nc"]
        )
        monkeypatch.setattr(speed.xr, "open_dataset", lambda *args, **kwargs: ds)
        monthly_mm = speed._load_monthly_pr(tmp_path, "GCM", "rcp45", [2021])
    np.testing.assert_allclose(monthly_mm.values[:, 0, 0], [86400 * 28, 86400 * 31])
    assert monthly_mm.attrs["units"] == "mm"


@pytest.mark.parametrize("loader", ["baseline", "future"])
def test_noleap_calendar_february_has_28_days_even_in_leap_year(
    monkeypatch, tmp_path, loader
):
    cftime = pytest.importorskip("cftime")
    import xarray as xr

    ds = xr.Dataset(
        {
            "pr": (
                ("time", "rlat", "rlon"),
                np.ones((1, 1, 1)),
                {"units": "kg m-2 s-1"},
            ),
            "time_bnds": (
                ("time", "bnds"),
                np.array(
                    [
                        [
                            cftime.DatetimeNoLeap(2020, 2, 1),
                            cftime.DatetimeNoLeap(2020, 3, 1),
                        ]
                    ],
                    dtype=object,
                ),
            ),
        },
        coords={"time": [cftime.DatetimeNoLeap(2020, 2, 15)], "rlat": [0], "rlon": [0]},
    )
    ds.time.attrs["bounds"] = "time_bnds"

    if loader == "baseline":
        speed = _import_speed_for_non_geospatial_test(monkeypatch)

        monkeypatch.setattr(speed, "find_nc_files", lambda *args: ["synthetic.nc"])
        monkeypatch.setattr(speed.xr, "open_mfdataset", lambda *args, **kwargs: ds)
        monthly_mm = speed.load_monthly_pr("GCM", "rcp45", "RCM", [2020])
    else:
        speed = _import_speed_for_non_geospatial_test(monkeypatch, future=True)

        monkeypatch.setattr(
            speed, "_find_nc_files", lambda *args: [tmp_path / "synthetic.nc"]
        )
        monkeypatch.setattr(speed.xr, "open_dataset", lambda *args, **kwargs: ds)
        monthly_mm = speed._load_monthly_pr(tmp_path, "GCM", "rcp45", [2020])
    assert monthly_mm.values[0, 0, 0] == pytest.approx(86400 * 28)


@pytest.mark.parametrize("future", [False, True])
def test_360_day_calendar_and_wrong_flux_unit_are_not_silently_misread(
    monkeypatch, future
):
    cftime = pytest.importorskip("cftime")
    import xarray as xr

    speed = _import_speed_for_non_geospatial_test(monkeypatch, future=future)
    ds = xr.Dataset(
        {
            "pr": (
                ("time", "rlat", "rlon"),
                np.ones((1, 1, 1)),
                {"units": "kg m-2 s-1"},
            )
        },
        coords={"time": [cftime.Datetime360Day(2020, 2, 15)], "rlat": [0], "rlon": [0]},
    )
    assert speed.precipitation_flux_to_monthly_mm(ds).item() == pytest.approx(
        86400 * 30
    )
    ds.pr.attrs["units"] = "mm/day"
    with pytest.raises(ValueError, match="Expected pr units"):
        speed.precipitation_flux_to_monthly_mm(ds)


@pytest.mark.xfail(
    strict=True,
    reason="Current simple Graph retains only the edge selected under baseline weight.",
)
def test_parallel_road_extreme_weight_can_choose_a_different_physical_edge(
    monkeypatch, tmp_path
):
    pytest.importorskip("geopandas")
    import geopandas as gpd
    from shapely.geometry import LineString
    from result1 import network_pipeline as network

    roads = gpd.GeoDataFrame(
        {
            "road_id": ["fast_baseline", "robust_alternative"],
            "Surface": ["unpaved", "unpaved"],
            "length_km": [10.0, 10.0],
        },
        geometry=[
            LineString([(0.0, 0.0), (0.1, 0.0)]),
            LineString([(0.0, 0.0), (0.1, 0.0)]),
        ],
        crs="EPSG:4326",
    )
    monkeypatch.setattr(gpd, "read_file", lambda _: roads.copy())
    speed_csv = tmp_path / "speed.csv"
    pd.DataFrame(
        {
            "road_id": ["fast_baseline", "robust_alternative"],
            "V_normal": [10.0, 5.0],
            "V_extreme": [1.0, 5.0],
            "passable_rate_extreme": [1.0, 1.0],
        }
    ).to_csv(speed_csv, index=False)
    g0, g1, _gconn, _edges, _coords = network.build_graphs_from_shp(
        tmp_path / "unused.shp", speed_csv
    )
    assert nx.shortest_path_length(g0, 0, 1, weight="weight") == pytest.approx(1.0)
    assert nx.shortest_path_length(g1, 0, 1, weight="weight") == pytest.approx(2.0)


def test_same_od_rerouting_is_no_slower_than_fixed_baseline_path():
    """A hand-checkable fixed-route decomposition using the existing function."""
    from result2.network_buffering_decomposition import compute_direct_degradation

    g0 = nx.Graph()
    g1 = nx.Graph()
    baseline = [("A", "B", 1.0), ("A", "C", 0.6), ("C", "B", 0.6)]
    extreme = [("A", "B", 2.0), ("A", "C", 0.6), ("C", "B", 0.6)]
    g0.add_weighted_edges_from(baseline)
    g1.add_weighted_edges_from(extreme)
    fixed = compute_direct_degradation(g0, g1, ["B"])["A"]
    t_reroute = nx.shortest_path_length(g1, "A", "B", weight="weight")
    assert fixed["t_normal_path"] == pytest.approx(1.0)
    assert fixed["t_g1_forced_path"] == pytest.approx(2.0)
    assert t_reroute == pytest.approx(1.2)
    assert t_reroute <= fixed["t_g1_forced_path"]


def test_missing_population_raster_is_not_valid_uniform_population(tmp_path):
    from data_procession import compute_health_accessibility as health

    missing_tif = tmp_path / "missing_worldpop.tif"
    with pytest.raises(RuntimeError, match="Population aggregation failed"):
        health.aggregate_population_to_nodes(
            missing_tif,
            node_list=[0, 1],
            lons=np.array([0.0, 0.1]),
            lats=np.array([0.0, 0.0]),
        )
