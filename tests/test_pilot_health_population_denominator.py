import numpy as np
from scipy.spatial import cKDTree

from hpc.pilot_health_population_denominator import spherical_xyz


def test_unit_sphere_embedding_and_antimeridian_order():
    xyz = spherical_xyz(np.array([179.9, -179.9, 0.0]), np.array([0.0, 0.0, 0.0]))
    np.testing.assert_allclose(np.linalg.norm(xyz, axis=1), 1.0, atol=1e-14)
    dist, idx = cKDTree(xyz[[1, 2]]).query(xyz[[0]])
    assert idx.tolist() == [0]
    assert dist[0] < 0.01


def test_high_latitude_longitude_converges():
    xyz = spherical_xyz(np.array([0.0, 1.0]), np.array([80.0, 80.0]))
    chord = np.linalg.norm(xyz[0] - xyz[1])
    assert chord * 6371.0 < 20.0  # fixed 111 km/degree would be badly wrong
