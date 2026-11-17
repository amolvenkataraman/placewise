import zipfile
from pathlib import Path

import pytest
import us_fixtures as fx
from regions_kit import US_REGIONS, use_regions
from timezones_kit import use_timezones

from packbuild import us
from packbuild.sources import SOURCES, url

LAYERS = ["states", "counties", "places", "cbsa", "csa", "zcta", "regions", "timezones"]
COUNTS = {
    "states": 3,
    "counties": 5,
    "places": 6,
    "cbsa": 4,
    "csa": 3,
    "zcta": 3,
    "regions": 2,
    "timezones": 5,
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
    store = tmp_path / "downloads"
    store.mkdir()
    files = {}
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

    def fake_write_pack(out_dir, name, version, layers, created=None):
        calls.append((out_dir, name, version, layers))
        return Path(out_dir) / f"{name}-{version}"

    monkeypatch.setattr(us, "write_pack", fake_write_pack)
    out = us.build_us(tmp_path / "cache", tmp_path / "out", "2026.11")
    assert out == tmp_path / "out" / "usa-2026.11"
    assert sorted(offline) == sorted(SOURCES["uscensus"].downloads.values())
    [(out_dir, name, version, layers)] = calls
    assert (out_dir, name, version) == (tmp_path / "out", "usa", "2026.11")
    assert [layer.name for layer in layers] == LAYERS
    assert {layer.name: len(layer.columns["id"]) for layer in layers} == COUNTS
    for layer in layers:
        curated = {"regions": "placewise-regions", "timezones": "placewise-timezones"}.get(layer.name)
        assert layer.sources == ((curated, "uscensus") if curated else ("uscensus",))
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
    assert at("counties", *park)["name"] == "San Francisco County"
    assert at("csa", *park)["name"] == "San Jose-San Francisco-Oakland, CA CSA"
    assert at("cbsa", *park)["type"] == "metro"
    assert at("states", *park)["usps"] == "CA"
    strip = at("places", 36.1147, -115.1728)
    assert (strip["name"], strip["lsad"], strip["population"]) == ("Paradise", "CDP", None)
    assert at("zcta", 36.1147, -115.1728)["name"] == "89109"
    reno = at("places", 39.5296, -119.8138)
    assert (reno["name"], reno["population"], reno["state"]) == ("Reno", 283621, "NV")
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

    # time zones: the AIANNH area first, then the split county, then the states
    assert at("timezones", 36.6, -114.6)["id"] == "tz:test-reservation"
    assert at("timezones", 36.6, -114.6)["zone"] == "America/Denver"
    washoe = at("timezones", 39.5296, -119.8138)
    assert (washoe["id"], washoe["zones"]) == ("tz:census:32031", "America/Los_Angeles|America/Denver")
    assert at("timezones", 36.1147, -115.1728)["id"] == "tz:iso:US-NV"
    assert at("timezones", *park)["zone"] == "America/Los_Angeles"


def test_a_region_member_missing_from_the_counties_fails_the_build(tmp_path, offline, monkeypatch):
    use_regions(monkeypatch, [*US_REGIONS, {**US_REGIONS[0], "id": "region:x", "members": ["census:06085"]}])
    with pytest.raises(ValueError, match="region:x: census:06085"):
        us.build_us(tmp_path / "cache", tmp_path / "out", "2026.11")


def test_main_builds_into_the_given_directories(tmp_path, offline, capsys):
    us.main(["--cache-dir", str(tmp_path / "cache"), "--out", str(tmp_path / "out"), "--version", "2026.11"])
    assert capsys.readouterr().out.strip() == str(tmp_path / "out" / "usa-2026.11")
