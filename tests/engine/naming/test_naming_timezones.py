"""Country packs whose finest units carry their time zone (the `tz` column on US counties and
Canadian subdivisions, packbuild.timezones): the zone of the unit the naming rules found the point
inside, a shape of the pack's `timezones` layer first, and the world's units elsewhere
(placewise.engine._timezones). naming_kit's synthetic packs, invented zones per unit."""

import pytest
from naming_kit import box, write_ca, write_us, write_world

from placewise.engine import Geocoder
from placewise.packs import LayerData

WORLD_TZ = {
    "iso:CA": "America/Toronto", "iso:IN": "Asia/Kolkata", "iso:US-NV": "America/Los_Angeles",
    "iso:US-NY": "America/New_York", "iso:US-CA": "America/Los_Angeles",
}  # fmt: skip


def _shapes(rows):
    """A shapes-only `timezones` layer: rows of (id, zone, box)."""
    cols = ("id", "name", "zone", "zones", "basis", "unit", "within", "country")
    columns = {c: [] for c in cols}
    for rid, zone, _ in rows:
        for c, v in zip(cols, (rid, rid, zone, "", "shape", "", "", "iso:US"), strict=True):
            columns[c].append(v)
    return LayerData(
        "timezones", "polygon", columns, ("synthetic",), features=[box(*r[2]) for r in rows],
        types=dict.fromkeys(cols, "str"),
    )  # fmt: skip


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    root = tmp_path_factory.mktemp("tz-units")
    county_zones = {
        "census:32003": "America/Los_Angeles",  # Clark
        "census:36047": "America/Chicago",  # Kings: not the world's New York, to tell them apart
        "census:06081": "America/Los_Angeles|America/Phoenix",  # San Mateo: split, its towns decide
    }
    shape = [("tz:test-box", "America/Denver", (10.0, -149.5, 10.05, -149.45))]  # inside Clark
    csd_zones = {"statcan:3520005": "America/Toronto", "statcan:3521005": "America/Winnipeg"}
    return Geocoder(
        packs=[
            write_world(root, tz=WORLD_TZ),
            write_us(root, tz=county_zones, extra=[_shapes(shape)]),
            write_ca(root, tz=csd_zones),
        ]
    )


def tz(geo, lat, lon):
    r = geo.lookup(lat, lon)
    return r.tz, r.sources.get("tz")


def test_a_point_takes_the_zone_of_the_county_it_is_in(geo):
    assert tz(geo, 10.3, -149.6) == ("America/Los_Angeles", "us/timezones:polygon")
    assert tz(geo, 10.75, -149.75) == ("America/Chicago", "us/timezones:polygon")


def test_a_shape_of_the_pack_wins_over_the_county(geo):
    assert tz(geo, 10.02, -149.47) == ("America/Denver", "us/timezones:polygon")


def test_a_split_county_lets_its_nearest_town_decide(geo):
    assert tz(geo, 10.7, -149.2) == ("America/Los_Angeles", "us/timezones:split")


def test_a_point_only_near_a_county_takes_the_worlds_unit(geo):
    # 0.5 km east of Kings County, in the water before San Mateo: the naming rules snap it to
    # Kings (and its admin1 to New York), but it is inside no county, so not Kings' zone: the
    # world's admin-1 unit answers
    assert tz(geo, 10.75, -149.495) == ("America/New_York", "world/timezones:polygon")


def test_canadian_subdivisions_carry_their_zones_and_the_rest_fall_back(geo):
    assert tz(geo, 10.75, -148.75) == ("America/Toronto", "ca/timezones:polygon")
    assert tz(geo, 10.25, -148.9) == ("America/Winnipeg", "ca/timezones:polygon")  # Mississauga
    assert tz(geo, 10.1, -148.2) == ("America/Toronto", "world/timezones:polygon")  # Fort Erie: no tz


def test_lookup_many_agrees_with_lookup(geo):
    lats, lons = (
        [10.3, 10.75, 10.02, 10.7, 10.75, 10.25],
        [-149.6, -149.75, -149.47, -149.2, -149.495, -148.9],
    )
    for r, lat, lon in zip(geo.lookup_many(lats, lons), lats, lons, strict=True):
        assert (r.tz, r.sources.get("tz")) == tz(geo, lat, lon)
