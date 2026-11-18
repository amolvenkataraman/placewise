"""packbuild.ind.crosswalk: each PIN area's LGD district, sub-district and city, on a synthetic grid
of PIN areas (0.01 degree squares, about 1.2 km2, near Bengaluru). Codes are LGD's real state
codes; districts, ULBs and villages are made up."""

import numpy as np
import pytest

from packbuild.ind import crosswalk as cw
from packbuild.ind.lgd import Directory, Unit
from packbuild.ind.names import Names
from packbuild.regions_layer import feature_rings
from placewise.model import Feature, Outline

X0, Y0, D = 77.5, 12.9, 0.01


def cell(col, row, size=1):
    """A PIN area's rings: the clockwise square at grid (col, row), `size` cells wide."""
    x, y = X0 + col * D, Y0 + row * D
    x1, y1 = X0 + (col + size) * D, Y0 + (row + size) * D  # so neighbours share exact vertices
    return [np.array([(x, y), (x, y1), (x1, y1), (x1, y)])]


def directory(**extra):
    d = Directory()
    d.states = {"29": Unit("29", "Karnataka", "", "IN-KA"), "7": Unit("7", "Delhi", "", "IN-DL")}
    d.districts = {
        "572": Unit("572", "Bengaluru Urban", "29", "IN-KA"),
        "573": Unit("573", "Bengaluru Rural", "29", "IN-KA"),
        "77": Unit("77", "New Delhi", "7", "IN-DL"),
    }
    d.subdistricts = {"5587": Unit("5587", "Bengaluru North", "29", "IN-KA", parent="572")}
    d.ulbs = {
        "900": Unit(
            "900", "Synthetic City Municipal Corporation", "29", "IN-KA", kind="Municipal Corporation"
        ),
        "901": Unit("901", "Synthetic Town Municipal Council", "29", "IN-KA", kind="Municipal Council"),
        "276400": Unit("276400", "North Delhi Municipal Corporation", "7", "IN-DL"),
        "276402": Unit("276402", "South Delhi Municipal Corporation", "7", "IN-DL"),
    }
    for k, v in extra.items():
        getattr(d, k).update(v)
    return d


def names(cities=()):
    return Names({}, tuple(cities), ())


def test_adjacency_measures_shared_borders():
    adj = cw.adjacency([cell(0, 0), cell(1, 0), cell(5, 5)])
    assert adj == {(0, 1): pytest.approx(D)}


def test_areas_whatever_the_input_winding():
    ring = ((12.9, 77.5), (12.9, 77.6), (13.0, 77.6), (13.0, 77.5))
    shape = Feature((Outline((ring,)),), {}, "x")
    flipped = Feature((Outline((tuple(reversed(ring)),)),), {}, "y")
    got = cw.areas_km2([feature_rings([shape]), feature_rings([flipped])])
    assert got[0] == pytest.approx(got[1]) and 120 < got[0] < 122  # 0.1 x 0.1 degrees at 13 N


def test_districts_by_villages_then_directory_then_ulb_then_neighbours():
    d = directory()
    d.pin_villages["560001"][("572", "5587")] = 3
    d.pin_villages["560001"][("573", "")] = 1
    d.pin_ulbs["560003"] = {"900"}
    d.pin_ulbs["560001"] = {"900"}
    pins = ["560001", "560002", "560003", "560004"]
    adj = cw.adjacency([cell(0, 0), cell(1, 0), cell(0, 1), cell(0, 2)])
    aliases = {("IN-KA", cw.folded("Bangalore Rural")): "573"}
    post = [("", ""), ("BANGALORE RURAL", "IN-KA"), ("", ""), ("", "")]
    district, sub, how = cw.districts(pins, d, post, aliases, adj)
    assert district == ["572", "573", "572", "572"]
    assert how == ["villages", "indiapost", "ulb", "neighbours"]
    assert sub == ["5587", "", "5587", "5587"]  # a sub-district spreads only within its district


def test_ulbs_take_lgd_rows_only_for_small_areas_in_the_same_state():
    d = directory()
    d.pin_ulbs["560001"] = {"900"}
    d.pin_ulbs["560002"] = {"900", "901"}  # the ULB with more member areas wins
    d.pin_ulbs["560003"] = {"276400"}  # another state's ULB: ignored
    d.pin_ulbs["560004"] = {"900"}  # too big to be part of a city
    pins = ["560001", "560002", "560003", "560004"]
    adj = cw.adjacency([cell(0, 5), cell(5, 5), cell(9, 9), cell(20, 20)])
    ulb, how = cw.ulbs(pins, d, ["29"] * 4, [5, 5, 5, 500], adj)
    assert ulb == ["900", "900", "", ""] and how == ["lgd", "lgd", "", ""]


def test_a_pin_code_listed_for_many_ulbs_is_an_office_address():
    d = directory()
    d.pin_ulbs["560001"] = {"900", "901", "902", "903"}
    d.ulbs |= {c: Unit(c, c, "29", "IN-KA") for c in ("902", "903")}
    ulb, _ = cw.ulbs(["560001"], d, ["29"], [5], {})
    assert ulb == [""]


def test_ulbs_spread_to_urban_neighbours_and_enclosed_villages():
    d = directory()
    d.pin_ulbs["560001"] = {"900"}
    d.pin_villages["560003"][("572", "5587")] = 2  # a village the city surrounds
    d.pin_villages["560004"][("572", "5587")] = 2  # a village on the city's edge
    # 560001 at (1,1), 560002 east of it (unlisted), 560003 north of it and ringed by listed
    # areas 560005-560007; 560004 beside 560005 touches the city on one side only
    rings = [cell(1, 1), cell(2, 1), cell(1, 2), cell(-1, 2), cell(0, 2), cell(2, 2), cell(1, 3)]
    pins = ["560001", "560002", "560003", "560004", "560005", "560006", "560007"]
    d.pin_ulbs["560005"] = d.pin_ulbs["560006"] = d.pin_ulbs["560007"] = {"900"}
    adj = cw.adjacency(rings)
    ulb, how = cw.ulbs(pins, d, ["29"] * 7, [1.2] * 7, adj, perimeter=cw.perimeters(rings))
    assert ulb[:4] == ["900", "900", "900", ""]
    assert how[:4] == ["lgd", "neighbours", "enclosed", ""]


def test_curated_cities_seed_their_pin_areas_and_merge_lgd_bodies():
    d = directory()
    d.pin_ulbs["110001"] = {"276400"}
    d.pin_ulbs["110002"] = {"276402"}
    cities = [
        {"id": "lgd:ulb:276600", "name": "Bengaluru", "state": "KA", "lgd": ["276600"],
         "pincodes": ["560001", "560002"]},
        {"id": "lgd:ulb:276402", "name": "Delhi", "state": "DL", "lgd": ["276400", "276401", "276402"]},
    ]  # fmt: skip
    pins = ["560001", "560002", "560003", "110001", "110002"]
    rings = [cell(0, 0), cell(1, 0), cell(2, 0), cell(30, 30), cell(31, 30)]
    d.pin_villages["560001"][("572", "5587")] = 1
    d.pin_villages["110001"][("77", "")] = 1
    post = [("", "")] * 5
    got = cw.build(pins, rings, post, d, names(cities))
    # BBMP (276600) is no longer in LGD; its unlisted urban neighbour joins it
    assert got.city == ["276600", "276600", "276600", "276402", "276402"]
    assert got.city_rule == ["seed", "seed", "neighbours", "lgd", "lgd"]
    assert got.district == ["572", "572", "572", "77", "77"] and got.state == ["29", "29", "29", "7", "7"]


def test_urban_areas_with_revenue_villages_but_no_branch_office_join_their_city():
    # LGD lists revenue villages in city PIN areas too (Mumbai Suburban); India Post's branch
    # offices are rural, so an area with villages and no branch office is still urban
    d = directory()
    d.pin_ulbs["560001"] = {"900"}
    d.pin_villages["560002"][("572", "5587")] = 2
    d.pin_villages["560003"][("572", "5587")] = 2
    pins, rings = ["560001", "560002", "560003"], [cell(0, 0), cell(1, 0), cell(2, 0)]
    adj = cw.adjacency(rings)
    ulb, how = cw.ulbs(pins, d, ["29"] * 3, [1.2] * 3, adj, branch_offices={"560003": 4})
    assert ulb == ["900", "900", ""] and how == ["lgd", "neighbours", ""]


def test_unlisted_areas_join_a_city_of_their_own_district_first():
    # Mulund (Mumbai Suburban) touches Thane's listed areas before Mumbai's spread reaches it
    d = directory(ulbs={"902": Unit("902", "Thane", "29", "IN-KA")})
    d.pin_ulbs["560001"] = {"900"}
    d.pin_ulbs["562004"] = {"902"}
    pins = ["560001", "560002", "560003", "562004"]
    rings = [cell(0, 0), cell(1, 0), cell(2, 0), cell(3, 0)]
    district = ["572", "572", "572", "573"]
    ulb, _ = cw.ulbs(pins, d, ["29"] * 4, [1.2] * 4, cw.adjacency(rings), district_of=district)
    assert ulb == ["900", "900", "900", "902"]


def test_unlisted_areas_join_a_city_whose_pin_block_they_share_first():
    # Mumbai Suburban's PIN codes (4000xx) are Mumbai's block though LGD lists only the island's
    d = directory(ulbs={"902": Unit("902", "Thane", "29", "IN-KA")})
    d.pin_ulbs["400001"] = {"900"}
    d.pin_ulbs["400601"] = {"902"}
    pins = ["400001", "400064", "400080", "400601"]
    rings = [cell(0, 0), cell(1, 0), cell(2, 0), cell(3, 0)]
    district = ["482", "483", "483", "497"]
    ulb, _ = cw.ulbs(pins, d, ["29"] * 4, [1.2] * 4, cw.adjacency(rings), district_of=district)
    assert ulb == ["900", "900", "900", "902"]
