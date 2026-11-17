"""Worldviews over disputed areas (worldview_kit): per-area views, admin1 per view, the curated
tables, flags only for disputed areas, warnings for views a pack lacks, the lock."""

import warnings

import numpy as np
import pytest
from worldview_kit import TABLES, write_world

from placewise.constants import worldviews as wv_const
from placewise.engine import Geocoder
from placewise.model import Settings, WorldviewSettings

NORTH_STRIP = (10.9, -148.5)
BETALAND = (10.3, -148.5)
GLACIER = (11.25, -149.75)
QUIET_STRIP = (10.1, -149.1)
GAMMALAND = (12.25, -149.75)
ODD_BIT = (10.1, -147.1)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    return write_world(tmp_path_factory.mktemp("worldviews"))


@pytest.fixture
def tables(monkeypatch):
    for name, value in TABLES.items():
        monkeypatch.setattr(wv_const, name, value)
    return monkeypatch


@pytest.fixture
def geo(world, tables):
    return Geocoder(packs=[world])


def test_a_whole_country_claim_is_no_dispute(geo):
    r = geo.lookup(*BETALAND)
    assert r.country.id == "iso:XB" and r.disputed is None
    r = geo.lookup(*BETALAND, worldview=("XD",))  # the view still decides the country
    assert r.country.id == "iso:XD" and r.disputed is None


def test_a_disputed_area_is_flagged_in_the_de_facto_view(geo):
    r = geo.lookup(*NORTH_STRIP)
    assert r.country.id == "iso:XB" and r.admin1.id == "iso:XB-E"
    d = r.disputed
    assert d.name == "North Strip"
    assert d.claimants == ("XA", "XB", "XD") and d.administered_by == "XB"
    assert d.applied_view == "de_facto" and d.views == {"de_facto": "XB", "XA": "XA", "XD": "XD"}


def test_a_view_moves_the_area_with_its_admin1_and_name(geo):
    r = geo.lookup(*NORTH_STRIP, worldview=("XA", "de_facto"))
    assert r.country.id == "iso:XA"
    assert r.admin1.id == "iso:XA-N" and r.sources["admin1"] == "world/admin1:worldview"
    assert r.disputed.name == "Alpha North" and r.disputed.applied_view == "XA"
    assert r.label.endswith("North Province, Alphaland")
    # the rest of Betaland stays Betaland in that view
    r = geo.lookup(*BETALAND, worldview=("XA", "de_facto"))
    assert r.country.id == "iso:XB" and r.admin1.id == "iso:XB-E" and r.disputed is None


def test_territorial_waters_of_an_area_belong_to_it(geo):
    r = geo.lookup(11.05, -148.5)  # 5.6 km off the North Strip
    assert r.sources["country"] == "world/countries:offshore"
    assert r.disputed.name == "North Strip"
    assert geo.lookup(11.05, -148.5, worldview=("XA",)).country.id == "iso:XA"


def test_a_unit_that_is_nobodys_country_answers_its_holder(geo):
    r = geo.lookup(*GLACIER)
    assert r.country.id == "iso:XA" and r.admin1.id == "iso:XA-N"
    assert r.disputed.claimants == ("XA", "XB") and r.disputed.administered_by == "XA"
    assert r.disputed.views == {"de_facto": "XA", "XB": "XB"}
    assert "NWG" not in repr(r.to_dict())
    r = geo.lookup(*GLACIER, worldview=("XB",))
    assert r.country.id == "iso:XB"
    assert r.admin1 is None  # no table entry: the glacier unit's own admin1 is never reported
    assert "NWG" not in repr(r.to_dict())


def test_areas_of_an_unflagged_holder_carry_no_flag(geo, tables):
    tables.setattr(wv_const, "UNFLAGGED_HOLDERS", frozenset({"AAA"}))
    geo = Geocoder(packs=[geo.packs[0]])
    assert geo.lookup(*QUIET_STRIP).country.id == "iso:XA"
    assert geo.lookup(*QUIET_STRIP).disputed is None
    r = geo.lookup(*QUIET_STRIP, worldview=("XB",))
    assert r.country.id == "iso:XB" and r.disputed is None
    assert r.admin1.id == "iso:XA-S"  # no table entry: the data's admin1 for that ground
    assert geo.lookup(*NORTH_STRIP).disputed is not None  # held by XB, still flagged


def test_a_view_table_merges_a_unit(geo):
    assert geo.lookup(*GAMMALAND).country.id == "iso:XC"
    r = geo.lookup(*GAMMALAND, worldview=("XA",))
    assert r.country.id == "iso:XA" and r.admin1.id == "iso:XC-01" and r.disputed is None


def test_an_area_column_naming_no_unit_falls_back_to_the_country_polygon(geo):
    r = geo.lookup(*ODD_BIT, worldview=("XA", "de_facto"))
    assert r.country.id == "iso:XD" and r.disputed is None


def test_the_disputed_entry_hides_disputed_areas_only(geo):
    r = geo.lookup(*NORTH_STRIP, worldview=("disputed", "de_facto"))
    assert r.country is None and r.disputed.applied_view == "disputed"
    assert geo.lookup(*BETALAND, worldview=("disputed", "de_facto")).country.id == "iso:XB"


def test_a_view_the_pack_lacks_warns_once_with_the_views_it_has(geo):
    expected = "'ZZ' is not in this pack.*available: de_facto, disputed, XA, XB, XD"
    with pytest.warns(UserWarning, match=expected):
        r = geo.lookup(*NORTH_STRIP, worldview=("ZZ", "de_facto"))
    assert r.country.id == "iso:XB" and r.disputed.applied_view == "de_facto"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        geo.lookup(*NORTH_STRIP, worldview=("ZZ", "de_facto"))


def test_the_lock_holds_over_areas(world, tables):
    settings = Settings(worldview=WorldviewSettings(order=("XA", "de_facto"), lock=True))
    geo = Geocoder(packs=[world], settings=settings)
    r = geo.lookup(*NORTH_STRIP, worldview=("de_facto",))
    assert r.country.id == "iso:XA" and r.admin1.id == "iso:XA-N"
    assert r.disputed.locked is True and r.disputed.applied_view == "XA"


@pytest.mark.parametrize("order", [None, ("XA", "de_facto"), ("XB",), ("disputed", "XD", "de_facto")])
def test_lookup_many_equals_lookup(geo, order):
    lat, lon = np.meshgrid(np.linspace(9.95, 12.6, 23), np.linspace(-150.1, -146.9, 29))
    lat, lon = lat.ravel(), lon.ravel()
    many = geo.lookup_many(lat, lon, worldview=order)
    for r, a, b in zip(many, lat, lon, strict=True):
        assert r.to_dict() == geo.lookup(float(a), float(b), worldview=order).to_dict()


def test_view_only_features_answer_only_under_their_view(geo):
    a = {"applied": np.array(["IN", "de_facto", "IN", "de_facto"], dtype=object)}
    pts = np.arange(4)
    rows = np.array([0, 0, 1, -1])
    flags = ["1", "", "0"]  # feature 0 is view-only
    assert geo.admin.view_only(a, pts, rows, flags, "IN").tolist() == [0, -1, 1, -1]
    assert geo.admin.view_only(a, pts, rows, None, "IN").tolist() == [0, 0, 1, -1]
    assert geo.admin.view_only(a, pts, rows, np.array([1, 0, 0]), "IN").tolist() == [0, -1, 1, -1]
