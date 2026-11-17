"""Worldviews end to end on the real world pack (and the India pack where built). Public places
only. For the areas India claims only the IN view is asserted (docs/worldviews.md)."""

from functools import cache

import pytest
from e2e_kit import geocoder, require_packs

from placewise.constants import worldviews as wv_const
from placewise.engine import Geocoder
from placewise.model import Settings, WorldviewSettings
from placewise.packs import open_pack

IN_VIEW = [
    # name, (lat, lon), admin1 id, Disputed.name in the IN view (None: not a disputed area)
    ("Gilgit", (35.9208, 74.3089), "iso:IN-LA", "Gilgit-Baltistan"),
    ("Skardu", (35.2971, 75.6333), "iso:IN-LA", "Gilgit-Baltistan"),
    ("Muzaffarabad", (34.3700, 73.4711), "iso:IN-JK", "Pakistan-occupied Kashmir"),
    ("Mirpur", (33.1478, 73.7518), "iso:IN-JK", "Pakistan-occupied Kashmir"),
    ("Aksai Chin", (35.2, 79.4), "iso:IN-LA", "Aksai Chin"),
    ("Shaksgam", (36.05, 76.6), "iso:IN-LA", "Shaksgam Valley"),
    ("Siachen", (35.42, 77.11), "iso:IN-LA", None),
    ("Leh", (34.1526, 77.5771), "iso:IN-LA", None),
    ("Srinagar", (34.0837, 74.7973), "iso:IN-JK", None),
    ("Tawang", (27.5860, 91.8594), "iso:IN-AR", None),
    ("Kalapani", (30.2167, 80.9900), "iso:IN-UT", None),
    ("Demchok", (32.70, 79.45), "iso:IN-LA", None),
]
SIACHEN, TAWANG, KALAPANI, DEMCHOK = (35.42, 77.11), (27.5860, 91.8594), (30.2167, 80.9900), (32.70, 79.45)
TAIPEI, HONG_KONG, MACAU = (25.0330, 121.5654), (22.2793, 114.1628), (22.1987, 113.5439)
BEIJING = (39.9042, 116.4074)


@cache
def _has_worldviews():
    [world] = require_packs("world")
    return wv_const.WORLDVIEWS in open_pack(world)


def _geo(*names):
    geo = geocoder(*names)
    if not _has_worldviews():
        pytest.skip("the world pack predates its worldviews layer: rebuild it (python -m packbuild.world)")
    return geo


@pytest.mark.parametrize(("name", "point", "admin1", "area"), IN_VIEW, ids=[p[0] for p in IN_VIEW])
def test_india_view_world_pack(name, point, admin1, area):
    r = _geo("world").lookup(*point, worldview="IN")
    assert r.cc == "IN" and r.country.name == "India"
    assert r.admin1.id == admin1
    if area is not None:
        assert r.disputed.name == area and r.disputed.applied_view == "IN"


@pytest.mark.parametrize(("name", "point", "admin1", "area"), IN_VIEW, ids=[p[0] for p in IN_VIEW])
def test_india_view_with_the_india_pack(name, point, admin1, area):
    r = _geo("world", "ind").lookup(*point, worldview=("IN", "de_facto"))
    assert r.cc == "IN" and r.admin1.id == admin1
    assert r.postal is not None and r.postal.id.startswith("pin:")  # the PIN layer agrees
    assert r.label.endswith(f"{r.admin1.name}, India")


def test_india_view_is_one_answer_for_many_points():
    geo = _geo("world", "ind")
    lats, lons = [p[1][0] for p in IN_VIEW], [p[1][1] for p in IN_VIEW]
    many = geo.lookup_many(lats, lons, worldview="IN")
    for r, lat, lon in zip(many, lats, lons, strict=True):
        assert r.to_dict() == geo.lookup(lat, lon, worldview="IN").to_dict()


@pytest.mark.parametrize("packs", [("world",), ("world", "ind")])
def test_siachen_is_india_by_default_never_a_pseudo_country(packs):
    r = _geo(*packs).lookup(*SIACHEN)
    assert r.cc == "IN" and r.admin1.id == "iso:IN-LA"
    text = repr(r.to_dict())
    assert "KAS" not in text and "Siachen Glacier" not in text


@pytest.mark.parametrize("point", [TAWANG, KALAPANI, DEMCHOK], ids=["Tawang", "Kalapani", "Demchok"])
def test_india_held_areas_are_india_by_default(point):
    assert _geo("world").lookup(*point).cc == "IN"


def test_taiwan_hong_kong_and_macau_are_countries_by_default():
    geo = _geo("world")
    assert geo.lookup(*TAIPEI).cc == "TW"
    assert geo.lookup(*HONG_KONG).cc == "HK"
    assert geo.lookup(*MACAU).cc == "MO"


def test_a_whole_country_claim_is_no_dispute():
    r = _geo("world").lookup(*BEIJING)
    assert r.cc == "CN" and r.disputed is None


@pytest.mark.parametrize("point", [HONG_KONG, MACAU, TAIPEI], ids=["Hong Kong", "Macau", "Taipei"])
def test_china_view(point):
    r = _geo("world").lookup(*point, worldview="CN")
    assert r.cc == "CN" and r.label.endswith("China")


def test_the_lock_holds_for_the_india_view():
    _geo("world")
    [world] = require_packs("world")
    settings = Settings(worldview=WorldviewSettings(order=("IN",), lock=True))
    geo = Geocoder(packs=[world], settings=settings)
    r = geo.lookup(35.9208, 74.3089, worldview=("de_facto",))
    assert r.cc == "IN" and r.admin1.id == "iso:IN-LA" and r.disputed.locked is True
    strict = Settings(worldview=WorldviewSettings(order=("IN",), lock=True, conflict="reject"))
    with pytest.raises(ValueError, match="worldview"):
        Geocoder(packs=[world], settings=strict).lookup(35.9208, 74.3089, worldview=("CN",))


def test_a_view_the_pack_lacks_warns_with_the_views_it_has():
    with pytest.warns(UserWarning, match=r"'FI' is not in this pack.*available: de_facto, disputed, .*IN"):
        r = _geo("world").lookup(*BEIJING, worldview=("FI", "de_facto"))
    assert r.cc == "CN"
