"""The Geocoder's packs on demand: in auto mode a batch fetches the country packs its points need
(once, before the lookup), a search fetches the packs its kinds and country ask for; manual and
locked modes never download. Releases are file:// directories built from synthetic packs."""

import json
import logging

import pytest

from placewise.engine import Geocoder
from placewise.model import DataSettings, Settings
from placewise.packs import archive, pack_info, write_index
from placewise.store import Store, net
from tests.engine.lookup_kit import write_world as write_lookup_world
from tests.engine.naming.naming_kit import write_in, write_us, write_world
from tests.engine.parks_kit import write_parks

LAS_VEGAS = (10.4, -149.9)  # in the synthetic "US" (naming_kit)
PIN_AREA = (10.25, -147.75)  # in the synthetic "IN"
ALPHA_PRESERVE = (0.75, -139.75)  # in Alphaland (lookup_kit), inside the usa-parks outlines


def _release(root, packs, meta=None):
    """A release directory of `packs` (archives and index.json); `meta` adds index fields."""
    out = root / "release"
    out.mkdir(exist_ok=True)
    infos = []
    for pack in packs:
        made = archive(pack)
        infos.append(pack_info(made.replace(out / made.name)))
    index = write_index(out, infos)
    if meta:
        doc = json.loads(index.read_text())
        for name, fields in meta.items():
            doc["packs"][name].update(fields)
        index.write_text(json.dumps(doc))
    return index.as_uri()


@pytest.fixture(autouse=True)
def _no_real_network_or_home(tmp_path, monkeypatch):
    monkeypatch.setenv("PLACEWISE_INDEX_URL", (tmp_path / "no-index-here" / "index.json").as_uri())
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "env-data"))


@pytest.fixture
def naming_release(tmp_path):
    built = tmp_path / "built"
    return _release(tmp_path, [write_world(built), write_us(built), write_in(built)])


def _geocoder(data_dir, index_url, **data):
    settings = Settings(data=DataSettings(**{"mode": "auto", **data}))  # manual is the default
    return Geocoder(settings=settings, store=Store(data_dir, settings.data, index_url=index_url))


def _no_network(monkeypatch):
    def refuse(url):
        raise AssertionError(f"tried to fetch {url}")

    monkeypatch.setattr(net, "_open", refuse)


def test_auto_fetches_the_country_pack_a_point_needs(tmp_path, naming_release, caplog):
    geo = _geocoder(tmp_path / "data", naming_release)
    assert geo.data_version == "world-2026.11"
    with caplog.at_level(logging.INFO, logger="placewise.store"):
        r = geo.lookup(*LAS_VEGAS)
    assert r.admin2 is not None and r.admin2.name == "Clark County"  # from the us pack
    assert geo.data_version == "world-2026.11+us-2026.11"
    assert any("downloading us" in rec.getMessage() for rec in caplog.records)
    assert "in" not in Store(tmp_path / "data").installed()  # nothing for countries not asked about


def test_a_batch_fetches_everything_it_needs_at_once_and_only_once(tmp_path, naming_release, monkeypatch):
    geo = _geocoder(tmp_path / "data", naming_release)
    fetched = []
    real = net.fetch_file
    monkeypatch.setattr(net, "fetch_file", lambda url, *a, **k: fetched.append(url) or real(url, *a, **k))
    lats, lons = zip(*[LAS_VEGAS, PIN_AREA, LAS_VEGAS], strict=True)
    results = geo.lookup_many(lats, lons)
    assert sorted(u.rsplit("/", 1)[1] for u in fetched) == ["in-2026.11.tar.xz", "us-2026.11.tar.xz"]
    assert results[0].admin2.name == "Clark County"
    assert results[1].postal is not None  # the in pack's PIN area
    geo.lookup_many(lats, lons)
    assert len(fetched) == 2


def test_the_answer_matches_a_geocoder_opened_with_the_packs(tmp_path, naming_release):
    geo = _geocoder(tmp_path / "data", naming_release)
    first = geo.lookup(*LAS_VEGAS)
    fresh = _geocoder(tmp_path / "data", naming_release, mode="locked")
    assert fresh.data_version == geo.data_version
    assert fresh.lookup(*LAS_VEGAS) == first


def test_manual_answers_with_what_is_installed_and_hints_once(tmp_path, naming_release, caplog):
    Store(tmp_path / "data", index_url=naming_release).fetch_index()  # as `placewise data list` leaves it
    geo = _geocoder(tmp_path / "data", naming_release, mode="manual")
    with caplog.at_level(logging.INFO, logger="placewise.store"):
        assert geo.lookup(*LAS_VEGAS).admin2 is None
        geo.lookup(*LAS_VEGAS)
    assert sum("placewise data install us" in rec.getMessage() for rec in caplog.records) == 1
    assert set(Store(tmp_path / "data").installed()) == {"world"}


@pytest.mark.parametrize("data", [{"mode": "locked"}, {"offline": True}])
def test_locked_never_touches_the_network(tmp_path, naming_release, monkeypatch, data):
    Store(tmp_path / "data", index_url=naming_release).install("world")
    _no_network(monkeypatch)
    geo = _geocoder(tmp_path / "data", naming_release, **data)
    assert geo.lookup(*LAS_VEGAS).admin2 is None
    geo.find("Las Vegas", country="US", kinds="locality")
    assert set(Store(tmp_path / "data").installed()) == {"world"}


def test_explicit_packs_are_never_extended(tmp_path, naming_release, monkeypatch):
    _no_network(monkeypatch)
    geo = Geocoder(packs=[write_world(tmp_path / "own")])
    assert geo.lookup(*LAS_VEGAS).admin2 is None and geo.data_version == "world-2026.11"


def test_a_search_fetches_the_country_its_context_names(tmp_path, naming_release):
    geo = _geocoder(tmp_path / "data", naming_release)
    geo.find("Las Vegas", country="US")
    assert "us" in Store(tmp_path / "data").installed()
    assert geo.data_version == "world-2026.11+us-2026.11"


def test_a_search_for_parks_fetches_the_park_packs_of_its_area(tmp_path):
    built = tmp_path / "built"
    outlines, points = write_parks(built)
    index_url = _release(
        tmp_path,
        [write_lookup_world(built), outlines, points],
        meta={"usa-parks": {"covers": ["XA"]}},  # the synthetic country the outlines are in
    )
    geo = _geocoder(tmp_path / "data", index_url)
    assert geo.parks is None
    geo.lookup(*ALPHA_PRESERVE)  # parks aren't in data.auto_packs: a lookup doesn't fetch them
    assert geo.parks is None
    geo.find("Alpha Preserve", kinds="park", near=ALPHA_PRESERVE)
    assert {p.name for p in geo.packs} == {"world", "usa-parks", "world-parks"}
    assert geo.parks is not None


def test_opted_in_kinds_come_with_lookups(tmp_path):
    built = tmp_path / "built"
    outlines, _ = write_parks(built)
    index_url = _release(
        tmp_path, [write_lookup_world(built), outlines], meta={"usa-parks": {"covers": ["XA"]}}
    )
    geo = _geocoder(tmp_path / "data", index_url, auto_packs=("country", "parks"))
    r = geo.lookup(*ALPHA_PRESERVE)
    assert "Alpha Preserve" in {p.name for p in r.within}
