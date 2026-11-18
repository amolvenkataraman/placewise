"""packbuild.regions_layer: members checked against the built layers, unions, and region rows."""

import numpy as np
import pytest

from packbuild import regions_layer as rl
from placewise.geo.shapes import contains
from placewise.model import Feature, Outline
from placewise.packs import open_pack
from placewise.packs.writer import write_pack


def square(x0, y0, size=1.0):
    """A clockwise (x east, y north) square, as shapefiles draw outer rings."""
    return np.array([(x0, y0), (x0, y0 + size), (x0 + size, y0 + size), (x0 + size, y0)], dtype=float)


def feature(fid, *rings_xy):
    """A Feature from (lon, lat) rings, first the shell then holes, in any winding."""
    rings = [tuple((float(y), float(x)) for x, y in r) for r in rings_xy]
    return Feature((Outline(tuple(rings)),), {}, fid)


def region(rid="region:test", members=("census:1", "census:2"), **extra):
    return {
        "id": rid,
        "short_name": "Test",
        "name": "Test region",
        "country": "US",
        "admin1": ["CA"],
        "aliases": ["Test Area", "TR"],
        "kind": "metro",
        "members": list(members),
        "definition": {"title": "t", "url": "https://example.org"},
        "notes": "",
        **extra,
    }


# --- membership --------------------------------------------------------------------------------


def test_check_members_passes_when_every_member_is_built():
    rl.check_members([region()], {"census:1", "census:2", "census:3"})


def test_check_members_fails_loudly_naming_every_missing_member():
    regions = [region(), region("region:other", members=("census:9",)), region("region:empty", members=())]
    with pytest.raises(ValueError) as e:
        rl.check_members(regions, {"census:1"})
    message = str(e.value)
    assert "region:test: census:2" in message and "region:other: census:9" in message
    assert "region:empty: no members" in message


def test_check_districts_needs_exactly_the_pin_areas_of_the_named_districts():
    rows = [("pin:1", "IN-DL", "NEW DELHI"), ("pin:2", "IN-DL", "South East"), ("pin:3", "IN-HR", "AMBALA")]
    ok = region(members=("pin:1", "pin:2"), districts={"DL": ["NEW DELHI", "SOUTH EAST"]})
    rl.check_districts([ok, region("region:no-districts")], rows)
    short = region(members=("pin:1",), districts={"DL": ["NEW DELHI", "SOUTH EAST"]})
    with pytest.raises(ValueError, match=r"region:test: missing pin:2"):
        rl.check_districts([short], rows)
    extra = region(members=("pin:1", "pin:2", "pin:3"), districts={"DL": ["NEW DELHI", "SOUTH EAST"]})
    with pytest.raises(ValueError, match=r"not in its districts: pin:3"):
        rl.check_districts([extra], rows)
    unknown = region(members=("pin:1",), districts={"DL": ["NEW DELHI", "NOWHERE"]})
    with pytest.raises(ValueError, match=r"no PIN area in DL NOWHERE"):
        rl.check_districts([unknown], rows)


# --- dissolve ----------------------------------------------------------------------------------


def _area(rings):
    from packbuild.polygons import signed_area

    return sum(signed_area(r) for r in rings)


def test_dissolve_drops_the_shared_edge_of_two_neighbours():
    rings = rl.dissolve([square(0, 0), square(1, 0)])
    assert len(rings) == 1 and len(rings[0]) == 6
    assert _area(rings) == pytest.approx(-2.0)  # still clockwise: a shell


def test_dissolve_keeps_an_enclosed_gap_as_a_hole():
    ring_of_eight = [square(x, y) for x in range(3) for y in range(3) if (x, y) != (1, 1)]
    rings = rl.dissolve(ring_of_eight)
    assert sorted(len(r) for r in rings) == [4, 12]
    assert _area(rings) == pytest.approx(-8.0)  # the 3x3 shell minus the 1x1 hole


def test_dissolve_splits_shapes_that_touch_at_one_corner_into_simple_rings():
    rings = rl.dissolve([square(0, 0), square(1, 1)])
    assert sorted(len(r) for r in rings) == [4, 4]
    assert all(len({tuple(p) for p in r}) == len(r) for r in rings)


def test_dissolve_of_nothing_is_nothing():
    assert rl.dissolve([]) == []


def test_union_answers_like_any_member_everywhere():
    members = [
        feature("a", square(0, 0, 2)),
        feature("b", square(2, 0, 2)),
        feature("c", square(5, 5, 1)),
        feature("d", square(0, 2, 4), square(1, 3, 1)[::-1]),  # a member with a hole
    ]
    union = rl.union("region:test", rl.feature_rings(members))
    assert union.id == "region:test"
    rng = np.random.default_rng(7)
    lat, lon = rng.uniform(-0.5, 6.5, 2000), rng.uniform(-0.5, 6.5, 2000)
    want = np.zeros(len(lat), dtype=bool)
    for m in members:
        for o in m.outlines:
            want |= contains(o.rings, lat, lon)
    got = np.zeros(len(lat), dtype=bool)
    for o in union.outlines:
        got ^= contains(o.rings, lat, lon)  # the pack reader's rule: even-odd over every ring
    assert np.array_equal(got, want)
    vertices = sum(len(r) for o in union.outlines for r in o.rings)
    assert vertices < sum(len(r) for m in members for o in m.outlines for r in o.rings)


def test_union_keeps_every_hole_no_shell_holds_as_its_own_part():
    # holes that touch their shell's boundary can fail the containment test: each is kept apart
    shell, lone_a, lone_b = square(0, 0, 4), square(10, 10)[::-1], square(20, 20)[::-1]
    union = rl.union("region:test", [shell, lone_a, lone_b])
    assert len(union.outlines) == 3


def test_feature_rings_normalise_winding():
    ccw = square(0, 0)[::-1]
    (ring,) = rl.feature_rings([feature("a", ccw)])
    assert _area([ring]) < 0


# --- the layer ---------------------------------------------------------------------------------


def _members():
    return {
        "census:1": feature("census:1", square(-122.5, 37.5, 0.5)),
        "census:2": feature("census:2", square(-122.0, 37.5, 0.5)),
        "census:3": feature("census:3", square(-122.5, 37.5, 0.25)),
    }


def test_layer_rows_smallest_first_with_area_and_joined_lists():
    small = region("region:small", members=("census:3",), aliases=[])
    big = region("region:big")
    layer = rl.from_features([big, small], _members(), ("uscensus",))
    assert layer.name == "regions" and layer.kind == "polygon"
    assert layer.sources == ("placewise-regions", "uscensus")
    c = layer.columns
    assert c["id"] == ["region:small", "region:big"]
    assert c["members"] == ["census:3", "census:1,census:2"]
    assert c["aliases"] == ["", "Test Area|TR"]
    assert c["kind"] == ["metro", "metro"] and c["country"] == ["US", "US"]
    assert c["short_name"] == ["Test", "Test"]
    # 1 x 0.5 degrees at 37.75 N is about 111.2 * 88 * 0.5 km²
    assert c["area_km2"][1] == pytest.approx(111.2 * 111.2 * np.cos(np.radians(37.75)) * 0.5, rel=0.01)
    assert c["area_km2"][0] == pytest.approx(c["area_km2"][1] / 8, rel=0.01)


def test_layer_build_fails_when_a_member_is_missing():
    with pytest.raises(ValueError, match="region:test: census:2"):
        rl.from_features([region()], {"census:1": _members()["census:1"]}, ("uscensus",))


def test_written_layer_gives_every_region_of_a_point(tmp_path):
    regions = [region("region:big"), region("region:small", members=("census:3",))]
    layer = rl.from_features(regions, _members(), ("uscensus",))
    pack = open_pack(write_pack(tmp_path, "us", "2026.11", [layer]))
    lyr = pack["regions"]
    ids = lambda lat, lon: [lyr.value("id", i) for i in lyr.query_all(lat, lon)]  # noqa: E731
    assert ids(37.6, -122.4) == ["region:small", "region:big"]
    assert ids(37.8, -121.7) == ["region:big"]
    assert ids(37.75, -122.0) == ["region:big"]  # on the dissolved shared edge's line
    assert ids(30.0, -140.0) == []
    assert lyr.value("id", lyr.query(37.6, -122.4)) == "region:small"  # smallest first
