import zipfile
from pathlib import Path

import pytest
from facts_kit import fixture_for
from timezones_kit import use_timezones

from packbuild import aliases, served, world, world_aliases
from packbuild.sources import SOURCES

DATA = Path(__file__).parent / "data"
LAYERS = ["countries", "admin1", "worldviews", "cities", "airports", "country_facts", "timezones"]


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
        "ne_10m_admin_0_disputed_areas": "ne_disputed_areas",
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
    with zipfile.ZipFile(store / "alternateNamesV2.zip", "w") as z:
        z.writestr(
            "alternateNamesV2.txt",
            "1\t6167865\tiata\tYYZ\t\t\t\t\t\t\n2\t6251999\ten\tDominion of Canada\t\t\t\t\t\t\n",
        )
    files["alternateNamesV2.zip"] = store / "alternateNamesV2.zip"
    curated = [
        {"text": "Bangalore", "kind": "former", "city": "Bengaluru", "country": "IN", "geonames": 1277333}
    ]
    monkeypatch.setattr(world_aliases, "curated", lambda: (aliases.for_packs(curated), {}))
    monkeypatch.setattr(served, "load", lambda: [])
    requested = []

    def fake_fetch(url, cache_dir, refresh=False):
        requested.append(url)
        name = url.rsplit("/", 1)[1]
        return files[name] if name in files else fixture_for(url)

    monkeypatch.setattr(world, "fetch", fake_fetch)
    use_timezones(monkeypatch)
    return requested


def test_build_world_fetches_every_source_and_hands_six_layers_to_the_writer(tmp_path, offline, monkeypatch):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None, names=None):
        assert names is not None and len(names) > 0  # every pack carries a name index
        calls.append((out_dir, name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(world, "write_pack", fake_write_pack)
    out = world.build_world(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "world-2026.11"
    # 3 Natural Earth zips, 4 GeoNames files, 1 OurAirports csv; then for the country facts
    # countryInfo again (cached), timeZones, 6 CLDR files, 1 Wikidata query and 2 CLDR date files
    assert len(offline) == 8 + 11
    [(out_dir, name, version, layers)] = calls
    assert (out_dir, name, version) == (tmp_path / "out", "world", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    counts = {layer.name: len(layer.columns["id"]) for layer in layers}
    assert counts == {
        "countries": 3, "admin1": 5, "worldviews": 2, "cities": 5, "airports": 5, "country_facts": 1,
        "timezones": 3,
    }  # fmt: skip
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
    assert [len(pack[name]) for name in LAYERS] == [3, 5, 2, 5, 5, 1, 3]  # facts: Ottawa is the one capital
    cities = pack["cities"]
    assert cities.row(int(cities.find("id", "geonames:7262586")[0]))["elevation"] is None
    countries = pack["countries"]
    assert countries.value("id", countries.query(43.65, -79.38)) == "iso:CA"
    assert countries.value("aliases", countries.query(43.65, -79.38)) == "Dominion of Canada"
    toronto = cities.row(int(cities.find("id", "geonames:6167865")[0]))
    bengaluru = cities.row(int(cities.find("id", "geonames:1277333")[0]))
    assert (toronto["airport_codes"], bengaluru["former_names"]) == ("YYZ", "Bangalore")
    airports = pack["airports"]
    yyz = airports.row(int(airports.find("id", "ourairports:CYYZ")[0]))
    assert yyz["served_city"] == "geonames:6167865"  # the nearby rule: Toronto
    toronto = pack.names.exact("Toronto")
    assert [pack.names.layers[x] for x in toronto.layer] == ["cities"]
    assert pack.names.codes("CA").layer.tolist() == [pack.names.layers.index("countries")]
    yyz = pack.names.codes("YYZ")  # the airport, and Toronto through its airport_codes
    assert {pack.names.layers[x] for x in yyz.layer} == {"airports", "cities"}
    bangalore = pack.names.exact("Bangalore")  # a former name
    assert [
        pack.names.resolve(int(x), int(r)).id for x, r in zip(bangalore.layer, bangalore.row, strict=True)
    ] == ["geonames:1277333"]
    zones = pack["timezones"]
    assert zones.value("zone", zones.query(43.65, -79.38)) == "America/Toronto"
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
