"""The curated regions as drawn in the real country packs' `regions` layer: public landmarks only.

Packs come from tests/e2e/e2e_kit.py (E2E_PACKS_DIR or the default build dirs); skipped
when a pack isn't built.
"""

from functools import cache

import pytest
from e2e_kit import require_packs

from packbuild import regions as dataset
from placewise.packs import open_pack


@cache
def _layer(name):
    (path,) = require_packs(name)
    pack = open_pack(path)
    if "regions" not in pack:
        pytest.skip(f"{path.name} was built before the regions layer")
    return pack["regions"]


def regions_at(name, lat, lon):
    layer = _layer(name)
    return {layer.value("id", int(i)) for i in layer.query_all(lat, lon)}


@pytest.mark.parametrize(
    ("pack", "point", "inside", "outside"),
    [
        (
            "can",
            (43.6426, -79.3871),
            {"region:gta", "region:gtha", "region:golden-horseshoe"},
            set(),
        ),  # CN Tower
        (
            "can",
            (43.2557, -79.8711),
            {"region:gtha", "region:golden-horseshoe"},
            {"region:gta"},
        ),  # Hamilton City Hall
        ("can", (43.0896, -79.0849), {"region:golden-horseshoe"}, {"region:gtha"}),  # Horseshoe Falls
        (
            "can",
            (43.4643, -80.5204),
            {"region:waterloo-region", "region:golden-horseshoe"},
            set(),
        ),  # Waterloo
        ("can", (49.2827, -123.1207), {"region:metro-vancouver"}, set()),  # Vancouver City Hall area
        ("can", (45.4236, -75.7009), {"region:ottawa-gatineau"}, set()),  # Parliament Hill
        ("can", (45.5088, -73.5878), {"region:greater-montreal"}, set()),  # Mount Royal
        ("usa", (37.8077, -122.4753), {"region:sf-bay-area"}, set()),  # Golden Gate Bridge, south end
        ("usa", (37.8324, -122.4795), {"region:sf-bay-area"}, set()),  # Golden Gate Bridge, north end
        ("usa", (37.4275, -122.1697), {"region:sf-bay-area"}, set()),  # Stanford main quad
        ("usa", (36.1147, -115.1728), {"region:las-vegas"}, set()),  # the Las Vegas Strip
        ("usa", (40.7580, -73.9855), {"region:new-york-metro"}, set()),  # Times Square
        ("usa", (38.8899, -77.0091), {"region:washington-metro"}, set()),  # US Capitol
        ("usa", (41.8789, -87.6359), {"region:chicagoland"}, set()),  # Willis Tower
        ("usa", (37.7456, -119.5936), set(), {"region:sf-bay-area"}),  # Yosemite Valley: in no region
        ("ind", (28.6129, 77.2295), {"region:delhi-ncr", "region:delhi-ncr-core"}, set()),  # India Gate
        (
            "ind",
            (28.495, 77.089),
            {"region:delhi-ncr", "region:delhi-ncr-core"},
            set(),
        ),  # Gurugram Cyber City
        ("ind", (27.1751, 78.0421), set(), {"region:delhi-ncr"}),  # Taj Mahal, Agra: outside the NCR
        ("ind", (18.9398, 72.8355), {"region:mumbai-metro-region"}, set()),  # Chhatrapati Shivaji Terminus
        (
            "ind",
            (12.9716, 77.5946),
            {"region:bengaluru", "region:bengaluru-metro-region"},
            set(),
        ),  # Cubbon Park
    ],
)
def test_landmark_regions(pack, point, inside, outside):
    found = regions_at(pack, *point)
    assert inside <= found, f"{point}: {sorted(found)}"
    assert not (outside & found), f"{point}: {sorted(found)}"
    if not inside:
        assert found == set()


def test_mid_span_of_the_golden_gate_is_water_in_no_county_so_in_no_region():
    # Census cartographic boundaries are clipped to the shoreline, and regions are their unions;
    # naming the region of a point on the water is the lookup's job (nearest land), not the layer's
    assert regions_at("usa", 37.8199, -122.4783) == set()


@pytest.mark.parametrize("pack", ["usa", "can", "ind"])
def test_open_ocean_is_in_no_region(pack):
    point = {"usa": (35.0, -140.0), "can": (45.0, -40.0), "ind": (10.0, 65.0)}[pack]
    assert regions_at(pack, *point) == set()


@pytest.mark.parametrize(("pack", "country"), [("usa", "US"), ("can", "CA"), ("ind", "IN")])
def test_every_curated_region_of_the_country_is_drawn_smallest_first(pack, country):
    layer = _layer(pack)
    ids = [layer.value("id", i) for i in range(len(layer))]
    assert sorted(ids) == sorted(r["id"] for r in dataset.load() if r["country"] == country)
    areas = [layer.value("area_km2", i) for i in range(len(layer))]
    assert areas == sorted(areas) and areas[0] > 0
    for i in range(len(layer)):
        row = layer.row(i)
        assert row["country"] == country and row["kind"] in dataset.KINDS and row["members"]


def _area(pack, rid):
    layer = _layer(pack)
    return layer.value("area_km2", int(layer.find("id", rid)[0]))


@pytest.mark.parametrize(
    ("pack", "rid", "member_layer"),
    [("can", "region:gta", "cd"), ("can", "region:gtha", "cd"), ("usa", "region:sf-bay-area", "counties")],
)
def test_a_union_covers_exactly_its_members(pack, rid, member_layer):
    from packbuild.regions_layer import region_area_km2

    (path,) = require_packs(pack)
    p = open_pack(path)
    members = _layer(pack).value("members", int(_layer(pack).find("id", rid)[0])).split(",")
    layer = p[member_layer]
    total = sum(region_area_km2(layer.feature(int(layer.find("id", m)[0]))) for m in members)
    assert _area(pack, rid) == pytest.approx(total, rel=0.002)  # Canada: simplified once, not per member


def test_the_ncr_has_about_the_area_its_planning_board_gives():
    # about 55,083 km² (NCRPB); PIN areas approximate the districts
    assert _area("ind", "region:delhi-ncr") == pytest.approx(55_083, rel=0.03)
