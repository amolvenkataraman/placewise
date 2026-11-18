import json
import zipfile
from pathlib import Path

import pytest
import us_depth_fixtures
import us_fixtures as fx
from regions_kit import US_REGIONS, use_regions
from timezones_kit import use_timezones

from packbuild import us
from packbuild.sources import SOURCES, url

LAYERS = ["states", "counties", "places", "cbsa", "csa", "postal_cities", "regions", "timezones"]
COUNTS = {
    "states": 3,
    "counties": 5,
    "places": 6,
    "cbsa": 4,
    "csa": 3,
    "postal_cities": 2,  # the ZCTAs whose postal city can name a locality: not Yosemite's
    "regions": 2,
    "timezones": 1,  # the AIANNH area; the zones are the counties' tz column
}


def _zip_shapefile(dest, shp):
    shp = Path(shp)
    with zipfile.ZipFile(dest, "w") as z:
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            z.write(shp.with_suffix(ext), f"{dest.stem}{ext}")
    return dest


def _zip_one(dest, path):
    with zipfile.ZipFile(dest, "w") as z:
        z.write(path, f"{dest.stem}.txt")
    return dest


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """fetch() replaced by fixture files laid out like the real downloads; no network."""
    inputs = fx.all_inputs(tmp_path / "fixtures")
    inputs.update(us_depth_fixtures.write(tmp_path / "fixtures"))
    store = tmp_path / "downloads"
    store.mkdir()
    files = {"US.zip": _zip_one(store / "US.zip", inputs["postal_us"])}  # GeoNames postal codes
    for name in us.DOWNLOADS:
        basename = url("uscensus", name).rsplit("/", 1)[1]
        target = store / basename
        if name in us.SHAPEFILES:
            files[basename] = _zip_shapefile(target, inputs[name])
        elif basename.endswith(".zip"):
            files[basename] = _zip_one(target, inputs[name])
        else:
            files[basename] = inputs[name]
    requested = []

    def fake_fetch(source_url, cache_dir, refresh=False):
        requested.append(source_url)
        return files[source_url.rsplit("/", 1)[1]]

    monkeypatch.setattr(us, "fetch", fake_fetch)
    use_regions(monkeypatch, US_REGIONS)
    use_timezones(monkeypatch)
    return requested


def test_every_download_is_in_the_registry():
    assert set(us.DOWNLOADS) == set(SOURCES["uscensus"].downloads)
    assert SOURCES["uscensus"].licence == "LicenseRef-public-domain"


def test_build_us_fetches_every_registry_url_and_hands_eight_layers_to_the_writer(
    tmp_path, offline, monkeypatch
):
    calls = []

    def fake_write_pack(out_dir, name, version, layers, created=None, names=None):
        assert names is not None and len(names) > 0  # every pack carries a name index
        calls.append((out_dir, name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(us, "write_pack", fake_write_pack)
    out = us.build_us(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "usa-2026.11"
    geonames = SOURCES["geonames"].downloads[us.GEONAMES_POSTAL]
    assert sorted(offline) == sorted([*SOURCES["uscensus"].downloads.values(), geonames])
    [(out_dir, name, version, layers)] = calls
    assert (out_dir, name, version) == (tmp_path / "out", "usa", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    assert {layer.name: len(layer.columns["id"]) for layer in layers} == COUNTS
    expected = {
        "regions": ("placewise-regions", "uscensus"),
        "postal_cities": ("uscensus",),
        "counties": ("uscensus", "placewise-timezones"),
        "timezones": ("placewise-timezones", "uscensus"),
    }
    for layer in layers:
        assert layer.sources == expected.get(layer.name, ("uscensus",))
        assert all(len(column) == COUNTS[layer.name] for column in layer.columns.values())
        assert set(layer.columns) == set(layer.types)


def test_build_us_writes_a_real_pack_that_answers_the_spot_checks(tmp_path, offline):
    from placewise.packs import open_pack

    path = us.build_us(tmp_path / "cache", tmp_path / "out", "2026.11")
    pack = open_pack(path, verify=True)
    assert [layer.name for layer in pack] == LAYERS
    assert {layer.name: len(layer) for layer in pack} == COUNTS
    assert set(pack.sources) == {"uscensus", "placewise-regions", "placewise-timezones"}

    def at(layer, lat, lon):
        i = pack[layer].query(lat, lon)
        return None if i < 0 else pack[layer].row(i)

    park = (37.7694, -122.4862)
    assert at("places", *park)["name"] == "San Francisco"
    sf = pack.names.exact("San Francisco")
    assert "places" in {pack.names.layers[x] for x in sf.layer}
    places = sf.layer == pack.names.layers.index("places")
    assert pack["places"].contains(sf.lat[places][0], sf.lon[places][0], int(sf.row[places][0]))
    assert at("counties", *park)["name"] == "San Francisco County"
    assert at("csa", *park)["name"] == "San Jose-San Francisco-Oakland, CA CSA"
    assert at("cbsa", *park)["type"] == "metro"
    assert at("states", *park)["usps"] == "CA"
    strip = at("places", 36.1147, -115.1728)
    assert (strip["name"], strip["lsad"], strip["population"]) == ("Paradise", "CDP", 185913)  # ACS
    assert (strip["population_source"], strip["principal"]) == ("acs5y2024", "29820")
    zip_ = at("postal_cities", 36.1147, -115.1728)  # the ZCTA, only as far as naming needs it
    assert (zip_["name"], zip_["postal_place"]) == ("89109", "census:3240000")
    assert set(pack["postal_cities"].fields) == {"id", "name", "postal_place"}
    assert at("postal_cities", 37.7456, -119.5936) is None  # Yosemite's postal city is no place
    assert not pack.names.codes("89109").layer.size  # ZIP Codes are found through usa-zip
    reno = at("places", 39.5296, -119.8138)
    assert (reno["name"], reno["population"], reno["state"]) == ("Reno", 283621, "NV")  # SUB-EST
    assert reno["population_source"] == "sub-est2025"
    # largest first; Henderson and Berkeley are not in the fixture's places
    assert at("cbsa", 36.1147, -115.1728)["principal_cities"] == "census:3240000,census:3254600"
    assert at("cbsa", *park)["principal_cities"] == "census:0667000,census:0653000"
    assert at("places", 37.7456, -119.5936) is None  # Yosemite Valley: no incorporated place or CDP
    assert at("counties", 37.7456, -119.5936)["name"] == "Mariposa County"

    regions = pack["regions"]
    bay = at("regions", *park)
    assert (bay["id"], bay["members"], bay["kind"], bay["country"]) == (
        "region:test-bay", "census:06075,census:06001", "metro", "US",
    )  # fmt: skip
    assert at("regions", 37.80, -121.6)["id"] == "region:test-bay"  # Alameda's part
    assert at("regions", 36.1147, -115.1728)["id"] == "region:test-vegas"
    assert at("regions", 37.7456, -119.5936) is None  # Mariposa is in no region
    assert regions.column("area_km2")[0] < regions.column("area_km2")[1]  # smallest first

    # time zones: the AIANNH area drawn; each county carries its own zone, else its state's
    assert at("timezones", 36.6, -114.6)["id"] == "tz:test-reservation"
    assert at("timezones", 36.6, -114.6)["zone"] == "America/Denver"
    assert at("timezones", 39.5296, -119.8138) is None
    assert at("counties", 39.5296, -119.8138)["tz"] == "America/Los_Angeles|America/Denver"  # Washoe
    assert at("counties", 36.1147, -115.1728)["tz"] == "America/Los_Angeles"  # Clark: Nevada's
    assert at("counties", *park)["tz"] == "America/Los_Angeles"


def test_a_region_member_missing_from_the_counties_fails_the_build(tmp_path, offline, monkeypatch):
    use_regions(monkeypatch, [*US_REGIONS, {**US_REGIONS[0], "id": "region:x", "members": ["census:06085"]}])
    with pytest.raises(ValueError, match="region:x: census:06085"):
        us.build_us(tmp_path / "cache", tmp_path / "out", "2026.11")


def test_main_builds_into_the_given_directories(tmp_path, offline, capsys):
    us.main(["--cache-dir", str(tmp_path / "cache"), "--out", str(tmp_path / "out"), "--version", "2026.11"])
    assert capsys.readouterr().out.strip() == str(tmp_path / "out" / "usa-2026.11")


def test_build_usa_zip_writes_the_zip_code_areas(tmp_path, offline):
    from packbuild import us_zip
    from placewise.packs import open_pack

    pack = open_pack(us_zip.build(tmp_path / "cache", tmp_path / "out", "2026.11"), verify=True)
    assert (pack.name, [layer.name for layer in pack]) == ("usa-zip", ["zcta"])
    assert len(pack["zcta"]) == 3 and set(pack.sources) == {"uscensus", "geonames"}
    manifest = json.loads((pack.path / "pack.json").read_text())
    assert (manifest["kind"], manifest["covers"], manifest["requires"]) == ("postal", ["US"], ["usa"])

    def at(lat, lon):
        i = pack["zcta"].query(lat, lon)
        return None if i < 0 else pack["zcta"].row(i)

    zip_ = at(36.1147, -115.1728)
    assert (zip_["name"], zip_["population"], zip_["postal_city"]) == ("89109", 6504, "Las Vegas")
    assert (zip_["postal_place"], zip_["postal_source"]) == ("census:3240000", "zbp")
    yosemite = at(37.7456, -119.5936)  # Business Patterns has no row: GeoNames' name
    assert (yosemite["postal_city"], yosemite["postal_place"], yosemite["postal_source"]) == (
        "Yosemite National Park",
        None,
        "geonames",
    )  # fmt: skip  ("" reads back as None)
    assert [pack.names.layers[x] for x in pack.names.codes("89109").layer] == ["zcta"]
