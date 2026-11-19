"""build_ca end to end on the tiny fixtures, with every download faked: no network."""

import json
import urllib.error
import urllib.parse
import zipfile
from pathlib import Path

import cgndb_fixtures
import pytest
import statcan_fixtures as fx
from regions_kit import CA_REGIONS, use_regions
from timezones_kit import use_timezones

from packbuild import arcgis, ca
from packbuild.sources import SOURCES, url
from packbuild.sources.can import cgndb, statcan
from placewise.packs import open_pack

BASE = ["provinces", "cd", "csd", "cma", "fsa"]
LAYERS = [*BASE, "populated_places", "regions"]  # can.json draws no shapes: no timezones layer
COUNTS = {
    "provinces": 3,
    "cd": 6,
    "csd": 8,
    "cma": 4,
    "fsa": 6,
    "populated_places": 5,
    "regions": 3,
}
BOUNDARY_DOWNLOADS = [
    (statcan.BOUNDARIES, "provinces"),
    (statcan.BOUNDARIES, "cd"),
    (statcan.BOUNDARIES, "csd"),
    (statcan.BOUNDARIES, "cma"),
    (statcan.FSA, "fsa"),
]
POPULATION_DOWNLOADS = [(statcan.POPULATION, k) for k in ("csd", "cma", "fsa")]
NAME_DOWNLOADS = [(cgndb.SOURCE, "populated_places")]


def _zip(path, members):
    with zipfile.ZipFile(path, "w") as z:
        for name, source in members.items():
            z.write(source, name)
    return path


@pytest.fixture
def downloads(tmp_path):
    """Fixture files laid out like the real downloads, by file name."""
    store = tmp_path / "downloads"
    shp_dir = tmp_path / "shp"
    files = {}
    for stem in fx.LAYERS:
        shp = fx.write_shapefile(shp_dir, stem)
        members = {f"{stem}{ext}": shp.with_suffix(ext) for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg")}
        store.mkdir(exist_ok=True)
        files[f"{stem}.zip"] = _zip(store / f"{stem}.zip", members)
    for table, csv_path in fx.POPULATION.items():
        files[f"{table}-eng.zip"] = _zip(store / f"{table}-eng.zip", {f"{table}.csv": csv_path})
    files["cgn_canada_csv_eng.zip"] = cgndb_fixtures.write_archive(store)
    return files


@pytest.fixture
def offline(downloads, monkeypatch):
    requested = []

    def fake_fetch(u, cache_dir, refresh=False):
        requested.append(u)
        return downloads[u.rsplit("/", 1)[1]]

    monkeypatch.setattr(ca, "fetch", fake_fetch)
    use_regions(monkeypatch, CA_REGIONS)
    use_timezones(monkeypatch)
    return requested


def test_the_registry_has_every_download_the_build_needs():
    for source_id, name in [*BOUNDARY_DOWNLOADS, *POPULATION_DOWNLOADS, *NAME_DOWNLOADS]:
        assert url(source_id, name).startswith("https://"), (source_id, name)
    for source_id in (statcan.BOUNDARIES, statcan.FSA, statcan.POPULATION):
        source = SOURCES[source_id]
        assert source.licence == "LicenseRef-StatCan-Open-Licence"
        assert source.credit.startswith("Adapted from Statistics Canada")
        assert "does not constitute an endorsement by Statistics Canada" in source.credit
    assert "Canada Post" in SOURCES[statcan.FSA].credit


def test_build_ca_fetches_from_the_registry_and_hands_six_layers_to_the_writer(
    tmp_path, offline, monkeypatch
):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None, names=None):
        assert names is not None and len(names) > 0  # every pack carries a name index
        calls.append((out_dir, name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(ca, "write_pack", fake_write_pack)
    out = ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "can-2026.11"
    expected = [*BOUNDARY_DOWNLOADS, *POPULATION_DOWNLOADS, *NAME_DOWNLOADS]
    assert sorted(offline) == sorted(url(s, n) for s, n in expected)
    [(out_dir, name, version, layers)] = calls
    assert (out_dir, name, version) == (tmp_path / "out", "can", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    assert {layer.name: len(layer.columns["id"]) for layer in layers} == COUNTS
    for layer in layers:
        assert set(layer.sources) <= set(SOURCES)
        assert set(layer.columns) == set(layer.types)


def test_build_ca_writes_a_pack_that_answers_for_public_places(tmp_path, offline):
    path = ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11")
    pack = open_pack(path, verify=True)
    assert [layer.name for layer in pack] == LAYERS
    assert {name: len(pack[name]) for name in LAYERS} == COUNTS
    assert set(pack.sources) == {
        statcan.BOUNDARIES, statcan.FSA, statcan.POPULATION, cgndb.SOURCE, "placewise-regions",
        "placewise-timezones",
    }  # fmt: skip
    i, km = pack["populated_places"].nearest(*fx.LAKE_LOUISE)
    assert pack["populated_places"].row(int(i))["name"] == "Lake Louise" and float(km) < 1
    louise = pack.names.exact("Lake Louise")
    assert "populated_places" in {pack.names.layers[x] for x in louise.layer}

    def names(lat, lon):
        out = {}
        for name in BASE:
            layer = pack[name]
            hits = layer.query_all(lat, lon)
            out[name] = [layer.value("name", int(i)) for i in hits]
        return out

    assert names(*fx.CN_TOWER) == {
        "provinces": ["Ontario"], "cd": ["Toronto"], "csd": ["Toronto"], "cma": ["Toronto"], "fsa": ["M5J"],
    }  # fmt: skip
    milton = names(*fx.MILTON_GO)
    assert (milton["csd"], milton["cd"], milton["cma"]) == (["Milton"], ["Halton"], ["Toronto"])
    assert names(*fx.MISSISSAUGA)["cd"] == ["Peel"]
    assert names(*fx.LAKE_LOUISE)["csd"] == ["Improvement District No. 9 Banff"]
    assert names(*fx.LAKE_LOUISE)["cma"] == []
    assert names(*fx.BANFF)["csd"] == ["Banff"]
    hill, gatineau = names(*fx.PARLIAMENT_HILL), names(*fx.GATINEAU)
    assert (hill["csd"], hill["provinces"]) == (["Ottawa"], ["Ontario"])
    assert (gatineau["csd"], gatineau["provinces"]) == (["Gatineau"], ["Quebec"])
    assert hill["cma"] == gatineau["cma"] == ["Ottawa - Gatineau"]

    csd = pack["csd"]
    row = csd.row(int(csd.find("id", "statcan:3524009")[0]))
    assert (row["csdtype"], row["province"], row["cduid"], row["population"]) == ("T", "ON", "3524", 132979)
    listuguj = csd.row(int(csd.find("id", "statcan:2406804")[0]))
    assert listuguj["population"] is None
    layer_json = json.loads((path / "fsa" / "layer.json").read_text())
    assert layer_json["sources"] == [statcan.FSA, statcan.POPULATION]


def _region_ids(pack, lat, lon):
    layer = pack["regions"]
    return [layer.value("id", int(i)) for i in layer.query_all(lat, lon)]


def test_build_ca_puts_each_subdivisions_zone_on_it(tmp_path, offline):
    csd = open_pack(ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11"))["csd"]

    def at(point):
        return csd.value("tz", csd.query(*point))

    assert at(fx.MILTON_GO) == "America/Atikokan"  # the subdivision's own, inside Halton's
    assert at(fx.CN_TOWER) == "America/Toronto"  # Ontario's
    assert at(fx.BANFF) == "America/Edmonton"
    pack = open_pack(csd_path := next((tmp_path / "out").glob("can-*")))
    cd, provinces = pack["cd"], pack["provinces"]
    assert cd.value("tz", cd.query(*fx.MILTON_GO)) == "America/Winnipeg"  # Halton's own entry
    assert cd.value("tz", cd.query(*fx.CN_TOWER)) is None  # Toronto division: no entry ("")
    assert provinces.value("tz", provinces.query(*fx.CN_TOWER)) == "America/Toronto"
    assert csd_path.name == "can-2026.11"


def test_build_ca_draws_regions_from_divisions_subdivisions_and_cmas(tmp_path, offline):
    pack = open_pack(ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11"), verify=True)
    assert _region_ids(pack, *fx.CN_TOWER) == ["region:test-gta"]
    assert _region_ids(pack, *fx.MISSISSAUGA) == ["region:test-gta"]
    assert sorted(_region_ids(pack, *fx.MILTON_GO)) == ["region:test-gta", "region:test-milton"]
    assert (
        _region_ids(pack, *fx.PARLIAMENT_HILL) == _region_ids(pack, *fx.GATINEAU) == ["region:test-capital"]
    )
    assert _region_ids(pack, *fx.BANFF) == []
    regions = pack["regions"]
    assert regions.value("id", 0) == "region:test-milton"  # smallest first
    gta = regions.feature(int(regions.find("id", "region:test-gta")[0]))
    assert gta.properties["members"] == "statcan:3520,statcan:3521,statcan:3524"
    # the union was simplified once: Toronto's dense edges are gone (the raw ring has ~200 vertices)
    assert sum(len(r) for o in gta.outlines for r in o.rings) < 40


def test_a_region_member_missing_from_the_census_layers_fails_the_build(tmp_path, offline, monkeypatch):
    use_regions(monkeypatch, [{**CA_REGIONS[0], "members": ["statcan:3525"]}])
    with pytest.raises(ValueError, match="region:test-gta: statcan:3525"):
        ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11")


def test_a_bot_check_on_the_file_server_suggests_the_map_service(tmp_path, monkeypatch):
    def blocked(u, cache_dir, refresh=False):
        raise urllib.error.HTTPError(u, 403, "Forbidden", {}, None)

    monkeypatch.setattr(ca, "fetch", blocked)
    with pytest.raises(RuntimeError, match="--via service"):
        ca.build_layers(tmp_path / "cache")


@pytest.fixture
def fake_service(downloads, monkeypatch):
    """ArcGIS REST answers for the boundary layers; population zips still come through fetch().
    Mississauga (CSD OBJECTID 2) times out unless asked for alone and generalised."""
    service = url(statcan.BOUNDARIES, "service")
    assert url(statcan.FSA, "service") == service  # FSAs are a layer of the same service
    fake = fx.FakeService(service, slow={"lcsd000b21a_e": [2]})
    monkeypatch.setattr(arcgis, "_get", fake)
    # fixture boxes are a few hundred km round: scale the request planning down to match
    monkeypatch.setattr(arcgis, "BATCH_KM", 300)
    monkeypatch.setattr(arcgis, "SOLO_KM", 500)
    monkeypatch.setattr(arcgis, "FULL_KM", 550)

    def fake_fetch(u, cache_dir, refresh=False):
        assert "/n1/tbl/csv/98100" in u or "cgn_canada" in u  # only the tables and CGNDB
        return downloads[u.rsplit("/", 1)[1]]

    monkeypatch.setattr(ca, "fetch", fake_fetch)
    use_regions(monkeypatch, CA_REGIONS)
    use_timezones(monkeypatch)
    return fake


def test_build_ca_via_the_map_service_gives_the_same_pack(tmp_path, fake_service):
    path = ca.build_ca(tmp_path / "cache", tmp_path / "out", "2026.11", via="service")
    pack = open_pack(path, verify=True)
    assert {name: len(pack[name]) for name in LAYERS} == COUNTS
    csd = pack["csd"]
    assert csd.value("name", int(csd.query_all(*fx.BANFF)[0])) == "Banff"
    assert csd.value("name", int(csd.query_all(*fx.MISSISSAUGA)[0])) == "Mississauga"
    # pages are cached with a sidecar naming what the service generalised: Banff National Park's
    # 610 km boundary by plan, Mississauga after its timeouts
    meta = json.loads((tmp_path / "cache" / "lcsd000b21s_e.json").read_text())
    assert meta["features"] == 8 and meta["url"].endswith("/2")
    assert meta["generalised_m"] == {"2": 25, "6": 25}
    assert len(list((tmp_path / "cache" / "lcsd000b21s_e").glob("page-*.json"))) == meta["pages"]
    # a second build doesn't ask the service again
    asked = len(fake_service.requests)
    ca.build_layers(tmp_path / "cache", via="service")
    assert len(fake_service.requests) == asked


def test_service_requests_are_planned_by_perimeter():
    lengths = [(1, 100), (2, 7950), (3, 12_000), (4, 50_000), (5, 10), (6, 10)]
    assert arcgis.plan(lengths, 8000, 10_000, 15_000, 500) == [
        ([1], None),
        ([2], None),
        ([3], None),  # alone, but small enough for full resolution
        ([4], 100),
        ([5, 6], None),
    ]
    assert arcgis.plan([(1, 1), (2, 1), (3, 1)], 8000, 10_000, 15_000, 2) == [([1, 2], None), ([3], None)]
    assert arcgis.generalisation(39_260) == 100  # Ontario
    assert arcgis.generalisation(190_692) == 400  # Nunavut
    assert arcgis.generalisation(10_000_000) == 1600


def test_a_feature_that_times_out_at_every_generalisation_is_an_error(tmp_path, monkeypatch):
    service = url(statcan.BOUNDARIES, "service")
    fake = fx.FakeService(service, slow={"lpr_000b21a_e": [1]})

    def hopeless(u, timeout=120):
        if "maxAllowableOffset" in u:
            raise urllib.error.HTTPError(u, 504, "Gateway Time-out", {}, None)
        return fake(u, timeout)

    monkeypatch.setattr(arcgis, "_get", hopeless)
    with pytest.raises(RuntimeError, match="1600 m"):
        arcgis.fetch_layer(service, "lpr_000b21s_e", tmp_path)
    assert not list(tmp_path.iterdir())  # nothing half-written


def test_errors_reported_inside_a_200_response_are_retried_too(tmp_path, monkeypatch):
    service = url(statcan.BOUNDARIES, "service")
    monkeypatch.setattr(
        arcgis, "_get", fx.FakeService(service, slow={"lcd_000b21a_e": [2, 3]}, json_errors=True)
    )
    folder = arcgis.fetch_layer(service, "lcd_000b21s_e", tmp_path)
    meta = json.loads((tmp_path / "lcd_000b21s_e.json").read_text())
    assert meta["features"] == 6 and meta["generalised_m"] == {"2": 25, "3": 25}
    assert len(statcan.census_divisions(folder).columns["id"]) == 6


def test_a_json_error_that_is_not_an_overload_is_raised(tmp_path, monkeypatch):
    service = url(statcan.BOUNDARIES, "service")
    fake = fx.FakeService(service)

    def broken(u, timeout=120):
        if "outFields=%2A" in u:
            return json.dumps({"error": {"code": 400, "message": "Invalid query"}}).encode()
        return fake(u, timeout)

    monkeypatch.setattr(arcgis, "_get", broken)
    with pytest.raises(ValueError, match="Invalid query"):
        arcgis.fetch_layer(service, "lcd_000b21s_e", tmp_path)


def test_a_client_side_read_timeout_is_retried_like_a_gateway_timeout(tmp_path, monkeypatch):
    service = url(statcan.BOUNDARIES, "service")
    fake = fx.FakeService(service)

    def slow(u, timeout=120):
        if "OBJECTID%3E%3D1+" in u and "maxAllowableOffset" not in u:
            raise urllib.error.URLError(TimeoutError("timed out"))
        return fake(u, timeout)

    monkeypatch.setattr(arcgis, "_get", slow)
    arcgis.fetch_layer(service, "lfsa000b21s_e", tmp_path, batch_km=1e9)
    meta = json.loads((tmp_path / "lfsa000b21s_e.json").read_text())
    assert meta["features"] == 6 and meta["generalised_m"] == {"1": 25}


def test_a_connection_failure_is_not_retried(tmp_path, monkeypatch):
    def refused(u, timeout=120):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(arcgis, "_get", refused)
    with pytest.raises(urllib.error.URLError):
        arcgis.fetch_layer(url(statcan.BOUNDARIES, "service"), "lfsa000b21s_e", tmp_path)
