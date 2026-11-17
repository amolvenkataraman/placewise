import numpy as np
import pytest

from placewise.geo import PolygonIndex
from placewise.model import Feature, Outline

SQUARE = Feature(
    outlines=(Outline((((0, 0), (0, 10), (10, 10), (10, 0)), ((4, 4), (4, 6), (6, 6), (6, 4)))),),
    properties={"name": "Square with hole"},
)
ISLANDS = Feature(
    outlines=(
        Outline((((0, 20), (0, 22), (2, 22), (2, 20)),)),
        Outline((((0, 30), (0, 32), (2, 32), (2, 30)),)),
    ),
    properties={"name": "Two islands"},
)
OVERLAP = Feature(
    outlines=(Outline((((8, 8), (8, 12), (12, 12), (12, 8)),)),), properties={"name": "Overlap"}
)
FEATURES = [SQUARE, ISLANDS, OVERLAP]


def _brute_force(lats, lons):
    out = np.full(len(lats), -1)
    for i, f in reversed(list(enumerate(FEATURES))):  # reversed: the first match wins
        out[f.contains(lats, lons)] = i
    return out


@pytest.mark.parametrize("cell_deg", [0.5, 1.0, 5.0])
def test_query_matches_brute_force_exactly(cell_deg):
    rng = np.random.default_rng(7)
    lats, lons = rng.uniform(-2, 14, 5000), rng.uniform(-2, 34, 5000)
    index = PolygonIndex(FEATURES, cell_deg=cell_deg)
    np.testing.assert_array_equal(index.query(lats, lons), _brute_force(lats, lons))


def test_scalar_queries_holes_and_overlaps():
    index = PolygonIndex(FEATURES)
    assert index.query(2, 2) == 0
    assert index.query(5, 5) == -1  # inside the hole
    assert index.query(1, 31) == 1
    assert index.query_all(9, 9) == [0, 2]  # in both the square and the overlap
    assert index.query_all(50, 50) == []


def test_empty_index():
    index = PolygonIndex([])
    assert index.query(1, 1) == -1
    assert list(index.query(np.array([1.0, 2.0]), np.array([1.0, 2.0]))) == [-1, -1]
