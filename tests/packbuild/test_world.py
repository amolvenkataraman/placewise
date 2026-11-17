import zipfile
from pathlib import Path

import pytest
from facts_kit import fixture_for

from packbuild import world
from packbuild.sources import SOURCES

DATA = Path(__file__).parent / "data"
LAYERS = ["countries", "admin1", "cities", "airports", "country_facts"]


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, source in members.items():
            z.write(source, name)
    return path


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """fetch() replaced by fixture files laid out like the real downloads; no network."""
    store = tmp_path / "downloads"
    store.mkdir()
    ne = {
        "ne_10m_admin_0_countries": "ne_countries",
        "ne_10m_admin_1_states_provinces": "ne_admin1",
    }
    files = {}
    for real, fixture in ne.items():
        members = {
            f"{real}{ext}": DATA / f"{fixture}{ext}" for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")
        }
        files[f"{real}.zip"] = _zip(store / f"{real}.zip", members)
    files["cities1000.zip"] = _zip(store / "cities1000.zip", {"cities1000.txt": DATA / "cities.txt"})
    for name in ("admin1CodesASCII.txt", "countryInfo.txt", "airports.csv"):
        files[name] = DATA / name
    requested = []

    def fake_fetch(url, cache_dir, refresh=False):
        requested.append(url)
        name = url.rsplit("/", 1)[1]
        return files[name] if name in files else fixture_for(url)

    monkeypatch.setattr(world, "fetch", fake_fetch)
    return requested


def test_build_world_fetches_every_source_and_hands_five_layers_to_the_writer(tmp_path, offline, monkeypatch):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None):
        calls.append((out_dir, name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(world, "write_pack", fake_write_pack)
    out = world.build_world(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "world-2026.11"
    # 2 Natural Earth zips, 3 GeoNames files, 1 OurAirports csv; then for the country facts
    # countryInfo again (cached), timeZones, 6 CLDR files, 1 Wikidata query and 2 CLDR date files
    assert len(offline) == 6 + 11
    [(out_dir, name, version, layers)] = calls
    assert (out_dir, name, version) == (tmp_path / "out", "world", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    counts = {layer.name: len(layer.columns["id"]) for layer in layers}
    assert counts == {"countries": 3, "admin1": 5, "cities": 5, "airports": 5, "country_facts": 1}
    for layer in layers:
        assert set(layer.sources) <= set(SOURCES)
        assert all(len(column) == counts[layer.name] for column in layer.columns.values())
        assert {"id", "name"} <= set(layer.columns)
        assert set(layer.columns) == set(layer.types)


def test_build_world_writes_a_real_pack_that_reopens(tmp_path, offline):
    from placewise.packs import open_pack

    path = world.build_world(tmp_path / "cache", tmp_path / "out", "2026.11")
    pack = open_pack(path, verify=True)
    assert [layer.name for layer in pack] == LAYERS
    assert [len(pack[name]) for name in LAYERS] == [3, 5, 5, 5, 1]  # facts: Ottawa is the one capital
    cities = pack["cities"]
    assert cities.row(int(cities.find("id", "geonames:7262586")[0]))["elevation"] is None
    countries = pack["countries"]
    assert countries.value("id", countries.query(43.65, -79.38)) == "iso:CA"
    facts = pack["country_facts"].row(0)
    assert (facts["id"], facts["capital"], facts["currency"], facts["point"]) == (
        "iso:CA",
        "Ottawa",
        "CAD",
        "capital",
    )


def test_every_source_licence_is_a_known_id():
    from placewise.constants import licences

    assert {s.licence for s in SOURCES.values()} <= licences.KNOWN
    assert not {s.licence for s in SOURCES.values()} & licences.SHARE_ALIKE  # world pack is not share-alike
