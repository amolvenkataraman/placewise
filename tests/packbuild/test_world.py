import zipfile
from pathlib import Path

import numpy as np
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
        "timezones": 1,
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
    assert [len(pack[name]) for name in LAYERS] == [3, 5, 2, 5, 5, 1, 1]  # facts: Ottawa is the one capital
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
    assert countries.value("tz", countries.query(43.65, -79.38)) == "America/Toronto"
    assert pack["admin1"].column("tz").tolist() == [""] * 5  # no country here is split
    zones = pack["timezones"]  # the hand-drawn shapes alone
    assert zones.value("zone", zones.query(50.5, -97.5)) == "America/Winnipeg"
    admin1 = pack["admin1"]
    ontario = admin1.row(int(admin1.find("id", "iso:CA-ON")[0]))
    assert ontario["population"] == 2794356 + 1017449  # Toronto and Ottawa

    def admin1_rank(name):
        found = pack.names.exact(name)
        return found.rank[found.layer == pack.names.layers.index("admin1")][0]

    assert admin1_rank("Ontario") > admin1_rank("Somaliland")  # no cities: the base
    facts = pack["country_facts"].row(0)
    assert (facts["id"], facts["capital"], facts["currency"], facts["point"]) == (
        "iso:CA",
        "Ottawa",
        "CAD",
        "capital",
    )


def test_admin1_population_is_the_people_of_its_cities(tmp_path):
    from placewise.packs import LayerData

    codes = tmp_path / "admin1CodesASCII.txt"
    rows = ("XX.01\tAlpha\tAlpha\t101", "XX.02\tBeta\tBeta\t102", "XX.03\tGámma\tGamma\t103")
    codes.write_text("\n".join(rows) + "\n", encoding="utf-8")
    admin1 = LayerData(
        "admin1", "point",
        {"id": ["iso:XX-A", "iso:XX-B", "iso:XX-C", "iso:XX-D"], "name": ["Alpha", "Beta", "Gamma", "Delta"],
         "country": ["XX"] * 4, "geonames": ["geonames:101", "geonames:102", "", ""]},
        ("synthetic",), lat=[0.0, 1.0, 2.0, 3.0], lon=[0.0, 1.0, 2.0, 3.0],
    )  # fmt: skip
    cities = LayerData(
        "cities", "point",
        {"id": ["c1", "c2", "c3", "c4", "c5"], "country": ["XX", "XX", "XX", "YY", "XX"],
         "admin1": ["01", "01", "01", "01", "03"], "feature_code": ["PPLA", "PPL", "PPLX", "PPL", "PPL"],
         "population": [1000, 500, 300, 7000, 40]},
        ("synthetic",), lat=[0.0] * 5, lon=[0.0] * 5,
    )  # fmt: skip
    out = world.admin1_population(admin1, cities, codes)
    # sections of a city (PPLX) are already in it; another country's 01 is not this one; without a
    # GeoNames id the unit is found by its name in its country; Beta and Delta have no cities
    assert out.columns["population"] == [1500, None, 40, None]
    assert out.types["population"] == "i8"


def test_world_admin1_rank_by_population_below_cities_of_their_size():
    from packbuild import name_specs
    from packbuild.names import rank_of

    specs = {spec.layer: spec for spec in name_specs.SPECS["world"]}
    people = {"population": np.array([20_000_000, 2_000_000, 80_000, -1])}
    admin1 = rank_of(specs["admin1"].rank, people, 4).tolist()
    assert admin1[0] > admin1[1] > admin1[2] == admin1[3]
    city = rank_of(specs["cities"].rank, people, 4).tolist()
    assert admin1[1] < city[1]  # Paris, the city, before Paris, the département


def test_every_source_licence_is_a_known_id():
    from placewise.constants import licences

    assert {s.licence for s in SOURCES.values()} <= licences.KNOWN
    assert not {s.licence for s in SOURCES.values()} & licences.SHARE_ALIKE  # world pack is not share-alike
