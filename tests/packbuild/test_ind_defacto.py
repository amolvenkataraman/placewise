"""packbuild.ind.defacto: PIN areas cut along the neighbours' de facto polygons. Synthetic boxes in
open Pacific water; "XO" and "Otherland" are invented.

lon -150 ............ -148 | -148 .......... -146
lat 11  India (iso:IN)     | Otherland (iso:XO)
        PIN A: -149 .. -148.5 (all in India); PIN areas span lat 10.2 - 10.7
        PIN B: -148.5 .. -147.5 (half on Otherland's ground)
        PIN C: -147.5 .. -147 (all on Otherland's ground)
lat 10  Nobody's Glacier (ne:KAS, lat 10.8-11, lon -149.5 .. -148): answered as India de facto
"""

import numpy as np
import pytest

from packbuild.ind import defacto
from packbuild.layer import LayerData
from packbuild.polygons import signed_area
from placewise.model import Feature, Outline


def box(south, west, north, east):
    """A Feature from a box: one ring of (lat, lon)."""
    return Feature(
        (
            Outline(
                (((south, west), (north, west), (north, east), (south, east)),),
            ),
        ),
        {},
        "",
    )


def rings(west, east, south=10.2, north=10.7):
    """A PIN area's rings in (lon, lat), clockwise (no edge runs along a country's edge)."""
    return [np.array([(west, south), (west, north), (east, north), (east, south)], dtype=np.float64)]


def area(rs):
    return -sum(signed_area(r) for r in rs)


@pytest.fixture(scope="module")
def neighbours():
    countries = LayerData(
        "countries", "polygon",
        {"id": ["iso:IN", "iso:XO", "ne:KAS"], "name": ["India", "Otherland", "Nobody's Glacier"],
         "adm0_a3": ["IND", "XOO", "KAS"]},
        ("synthetic",),
        features=[box(10, -150, 11, -148), box(10, -148, 11, -146), box(10.8, -149.5, 11, -148)],
    )  # fmt: skip
    return defacto.Neighbours(countries)


def test_neighbours_leave_out_india_and_units_answered_as_india(neighbours):
    assert neighbours.rows == [1]
    assert neighbours.contains(np.array([-147.0, -149.0]), np.array([10.5, 10.9])).tolist() == [True, False]


def test_a_pin_area_is_cut_along_the_neighbours_border(neighbours):
    india, claimed = neighbours.split(rings(-148.5, -147.5))
    assert area(india) == pytest.approx(0.25) and area(claimed) == pytest.approx(0.25)
    assert all(r[:, 0].max() <= -148 for r in india) and all(r[:, 0].min() >= -148 for r in claimed)


def test_pieces_flag_the_parts_on_a_neighbours_ground(neighbours):
    pieces = defacto.pieces([rings(-149, -148.5), rings(-148.5, -147.5), rings(-147.5, -147)], neighbours)
    assert [(p.pin, p.view_only) for p in pieces] == [(0, False), (1, False), (1, True), (2, True)]
    assert pieces[0].rings[0] is not None and np.array_equal(pieces[0].rings[0], rings(-149, -148.5)[0])
