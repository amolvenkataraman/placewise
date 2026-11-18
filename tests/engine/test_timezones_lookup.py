"""Result.tz from the zones the packs give their units (placewise.engine._timezones) on lookup_kit's
synthetic world, with invented zone names (the engine doesn't check them; packbuild does). Every
world-pack test runs on both forms of the same zones: the `tz` column on the countries and admin1
layers with the shape alone drawn ("columns"), and packs built before it, whose `timezones` layer
copies each unit's outline ("polygons"):
  tz:tip           shape inside North Province, the box 0.9-1.0 N, 140.0-139.9 W   Pacific/Tip
  tz:iso:XA-N      North Province                                                  Pacific/North
  tz:iso:XA-S      South Province, split between Pacific/South and Pacific/Alpha (towns decide)
  tz:iso:XB        Betaland, whole                                                 Pacific/Beta
  tz:iso:XC        Gammaland: no zone ("": the nearest-city rule answers)
"""

import dataclasses

import numpy as np
import pytest
from lookup_kit import CITIES, CREATED, admin1_layer, airports_layer, box_feature, countries_layer

from placewise.engine import Geocoder
from placewise.model import Feature, Settings, WorldviewSettings
from placewise.packs import LayerData, write_pack

TZ_COLUMNS = ("id", "name", "zone", "zones", "basis", "unit", "within", "country")
SOUTHPORT = ("geonames:10", "Southport", 0.1, -139.9, "XA", 3_000, "PPL", "Pacific/South")


def tz_layer(rows):
    """rows: (id, zone, zones, basis, unit, within, country, Feature)"""
    columns = {c: [] for c in TZ_COLUMNS}
    features = []
    for rid, zone, zones, basis, unit, within, country, feature in rows:
        for c, v in zip(TZ_COLUMNS, (rid, rid, zone, zones, basis, unit, within, country), strict=True):
            columns[c].append(v)
        features.append(Feature(feature.outlines, {}, rid))
    return LayerData(
        "timezones",
        "polygon",
        columns,
        ("synthetic",),
        features=features,
        types=dict.fromkeys(TZ_COLUMNS, "str"),
    )


WORLD_TZ = [
    ("tz:tip", "Pacific/Tip", "", "shape", "", "iso:XA-N", "iso:XA", box_feature(0.9, -140.0, 1.0, -139.9)),
    ("tz:iso:XA-N", "Pacific/North", "", "admin1", "iso:XA-N", "", "iso:XA", box_feature(0.5, -140, 1, -139)),
    (
        "tz:iso:XA-S",
        "Pacific/South",
        "Pacific/South|Pacific/Alpha",
        "admin1",
        "iso:XA-S",
        "",
        "iso:XA",
        box_feature(0, -140, 0.5, -139),
    ),
    ("tz:iso:XB", "Pacific/Beta", "", "country", "iso:XB", "", "iso:XB", box_feature(0, -139, 1, -138)),
    ("tz:iso:XC", "", "", "country", "iso:XC", "", "iso:XC", box_feature(2, -140, 2.5, -139.5)),
]


def cities_layer():
    rows = [*CITIES, SOUTHPORT]
    columns = {
        "id": [c[0] for c in rows],
        "name": [c[1] for c in rows],
        "country": [c[4] for c in rows],
        "admin1": [""] * len(rows),
        "feature_code": [c[6] for c in rows],
        "population": np.array([c[5] for c in rows], dtype=np.int64),
        "timezone": [c[7] for c in rows],
    }
    lat, lon = np.array([c[2] for c in rows]), np.array([c[3] for c in rows])
    return LayerData("cities", "point", columns, ("synthetic",), lat=lat, lon=lon)


def write(out_dir, name, layers):
    return write_pack(out_dir, name, "2026.11", layers, created=CREATED)


def with_tz(layer, zones):
    """`layer` with a `tz` column: zones {id: tz}, "" for the others."""
    column = [zones.get(i, "") for i in layer.columns["id"]]
    return dataclasses.replace(
        layer, columns={**layer.columns, "tz": column}, types={**layer.types, "tz": "str"}
    )


def columns_world(rows=WORLD_TZ):
    """WORLD_TZ as the packs carry it now: each unit's zone on its own row, the shapes drawn."""
    tz = {}
    for _, zone, zones, basis, unit, *_ in rows:
        if basis != "shape":
            tz[unit] = zones or zone or "-"
    countries, admin1 = with_tz(countries_layer(), tz), with_tz(admin1_layer(), tz)
    return [
        countries,
        admin1,
        cities_layer(),
        airports_layer(),
        tz_layer([r for r in rows if r[3] == "shape"]),
    ]


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    root = tmp_path_factory.mktemp("tz")
    base = [countries_layer(), admin1_layer(), cities_layer(), airports_layer()]
    world = write(root / "with", "world", [*base, tz_layer(WORLD_TZ)])
    plain = write(root / "without", "world", base)
    # a country pack for Alphaland: one finer part inside South Province, then the whole country
    alpha = write(
        root / "with",
        "alp",
        [
            tz_layer(
                [
                    (
                        "tz:part",
                        "Pacific/Fine",
                        "",
                        "part",
                        "p:1",
                        "",
                        "iso:XA",
                        box_feature(0.0, -139.6, 0.1, -139.4),
                    ),
                    (
                        "tz:iso:XA",
                        "Pacific/Coarse",
                        "",
                        "admin1",
                        "iso:XA",
                        "",
                        "iso:XA",
                        box_feature(0, -140, 1, -139),
                    ),
                ]
            )
        ],
    )
    # the same world layer in a pack of its own: answered by geometry, not through the admin units
    alone = write(root / "alone", "zones", [tz_layer(WORLD_TZ)])
    columns = write(root / "columns", "world", columns_world())
    return {"world": world, "plain": plain, "alp": alpha, "alone": alone, "columns": columns}


@pytest.fixture(scope="module", params=["polygons", "columns"])
def geo(packs, request):
    return Geocoder(packs=[packs["world" if request.param == "polygons" else "columns"]])


def test_the_columns_world_draws_only_its_shape(packs):
    from placewise.packs import open_pack

    pack = open_pack(packs["columns"])
    assert pack["timezones"].column("id").tolist() == ["tz:tip"]
    assert pack["countries"].column("tz").tolist() == ["", "Pacific/Beta", "-"]
    assert pack["admin1"].column("tz").tolist()[:2] == ["Pacific/North", "Pacific/South|Pacific/Alpha"]


def tz(geo, lat, lon, **kw):
    r = geo.lookup(lat, lon, **kw)
    return r.tz, r.sources.get("tz")


def test_a_whole_country_takes_its_zone_from_the_polygon(geo):
    assert tz(geo, 0.5, -138.75) == ("Pacific/Beta", "world/timezones:polygon")


def test_an_admin1_unit_takes_its_own_zone_over_the_nearest_towns(geo):
    # Alpha City's GeoNames zone is Pacific/Alpha; North Province's polygon says Pacific/North
    assert tz(geo, 0.75, -139.5) == ("Pacific/North", "world/timezones:polygon")


def test_a_shape_wins_inside_its_unit(geo):
    assert tz(geo, 0.95, -139.95) == ("Pacific/Tip", "world/timezones:polygon")


def test_in_a_split_unit_the_nearest_town_with_one_of_its_zones_decides(geo):
    assert tz(geo, 0.12, -139.88) == ("Pacific/South", "world/timezones:split")  # by Southport
    assert tz(geo, 0.25, -139.2) == ("Pacific/Alpha", "world/timezones:split")  # by Southby


def test_a_unit_without_a_zone_falls_back_to_the_nearest_city(geo):
    assert tz(geo, 2.25, -139.75) == ("Pacific/Gamma", "world/cities:nearest")


def test_offshore_within_territorial_waters_takes_the_country_unit(geo):
    assert tz(geo, 1.1, -139.5) == ("Pacific/North", "world/timezones:offshore")


def test_far_at_sea_there_is_no_zone(geo):
    r = geo.lookup(-30.0, -100.0)
    assert r.tz is None and "tz" not in r.sources


def test_the_finest_pack_wins_and_its_gaps_fall_back_to_the_world(packs):
    geo = Geocoder(packs=[packs["world"], packs["alp"]])
    assert tz(geo, 0.05, -139.5) == ("Pacific/Fine", "alp/timezones:polygon")
    assert tz(geo, 0.75, -139.5) == ("Pacific/Coarse", "alp/timezones:polygon")
    assert tz(geo, 1.1, -139.5) == ("Pacific/North", "world/timezones:offshore")  # outside alp's polygons
    assert tz(geo, 0.5, -138.75) == ("Pacific/Beta", "world/timezones:polygon")  # alp is Alphaland's only


def test_a_timezones_layer_outside_the_world_pack_is_answered_by_geometry(packs):
    geo = Geocoder(packs=[packs["plain"], packs["alone"]])
    assert tz(geo, 0.5, -138.75) == ("Pacific/Beta", "zones/timezones:polygon")
    assert tz(geo, 0.95, -139.95) == ("Pacific/Tip", "zones/timezones:polygon")
    assert tz(geo, 0.12, -139.88) == ("Pacific/South", "zones/timezones:split")
    assert tz(geo, 2.25, -139.75) == ("Pacific/Gamma", "world/cities:nearest")


def test_without_a_timezones_layer_the_nearest_city_answers_as_before(packs):
    geo = Geocoder(packs=[packs["plain"]])
    assert tz(geo, 0.75, -139.5) == ("Pacific/Alpha", "world/cities:nearest")


def test_a_worldview_that_reports_a_one_zone_country_takes_that_zone(packs, tmp_path):
    # make Alphaland one zone; Gammaland is reported as Alphaland under Alphaland's view
    rows = [r for r in WORLD_TZ if r[6] != "iso:XA"]
    rows.append(
        ("tz:iso:XA", "Pacific/Alpha", "", "country", "iso:XA", "", "iso:XA", box_feature(0, -140, 1, -139))
    )
    base = [countries_layer(), admin1_layer(), cities_layer(), airports_layer()]
    for form, layers in (("polygons", [*base, tz_layer(rows)]), ("columns", columns_world(rows))):
        geo = Geocoder(packs=[write(tmp_path / form, "world", layers)])
        assert tz(geo, 2.25, -139.75, worldview="xa") == ("Pacific/Alpha", "world/timezones:worldview")
        assert tz(geo, 2.25, -139.75) == ("Pacific/Gamma", "world/cities:nearest")  # de facto: no zone
        settings = Settings(worldview=WorldviewSettings(order=("XA", "de_facto"), lock=True))
        locked = Geocoder(packs=[geo.packs[0]], settings=settings)
        assert tz(locked, 2.25, -139.75, worldview=("de_facto",)) == (
            "Pacific/Alpha",
            "world/timezones:worldview",
        )


def test_lookup_many_agrees_with_lookup(geo):
    lats = [0.5, 0.75, 0.95, 0.12, 0.25, 2.25, 1.1, -30.0]
    lons = [-138.75, -139.5, -139.95, -139.88, -139.2, -139.75, -139.5, -100.0]
    many = geo.lookup_many(lats, lons)
    for r, lat, lon in zip(many, lats, lons, strict=True):
        one = geo.lookup(lat, lon)
        assert (r.tz, r.sources.get("tz")) == (one.tz, one.sources.get("tz"))
