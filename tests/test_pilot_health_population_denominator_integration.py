from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("osgeo")
pytest.importorskip("pyproj")
pytest.importorskip("pyarrow")
from osgeo import gdal, osr
from shapely.geometry import box

from hpc.pilot_health_population_denominator import run


def test_synthetic_population_boundary_and_distance(tmp_path: Path):
    tif = tmp_path / "tiny.tif"
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(str(tif), 3, 2, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((0, 1, 0, 2, 0, -1))
    crs = osr.SpatialReference()
    crs.ImportFromEPSG(4326)
    ds.SetProjection(crs.ExportToWkt())
    ds.GetRasterBand(1).WriteArray(np.array([[1, 2, 0], [3, -99999, 4]], dtype=np.float32))
    ds.GetRasterBand(1).SetNoDataValue(-99999)
    ds = None

    gpkg = tmp_path / "boundary.gpkg"
    gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 2, 2)], crs="EPSG:4326").to_file(gpkg)
    facilities = tmp_path / "health.csv"
    facilities.write_text("fid,country,lon,lat\n1,Tiny,0.5,1.5\n")
    out = tmp_path / "out"
    result = run(Namespace(country="Tiny", iso3="TNY", population_tif=tif,
                           boundary_gpkg=gpkg, facilities_csv=facilities, out_dir=out))
    assert result["status"] == "PILOT_INPUT_ONLY_NOT_SCIENTIFIC_RELEASE"
    assert result["positive_pixels"] == 4
    assert result["inside_pixels"] == 3
    assert result["outside_pixels"] == 1
    assert result["population_positive_tif"] == 10
    assert result["population_inside_country_center"] == 6
    assert result["population_outside_country_center"] == 4
    assert result["facility_distance_min_km_pilot"] == pytest.approx(0, abs=1e-7)
    assert (out / "TNY_population_facility_distance_pilot.parquet").exists()
