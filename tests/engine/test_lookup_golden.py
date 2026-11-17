"""Golden answers from the real world pack (Natural Earth, GeoNames, OurAirports), public places
only. Skipped when the pack hasn't been built: uv run python -m packbuild.world --version 2026.11"""

from pathlib import Path

import numpy as np
import pytest

from placewise.engine import Geocoder

PACK = Path(__file__).resolve().parents[2] / ".cache" / "packbuild" / "out" / "world-2026.11"

pytestmark = pytest.mark.skipif(not (PACK / "pack.json").is_file(), reason="world pack not built")


@pytest.fixture(scope="module")
def geo():
    return Geocoder(packs=[PACK])


# name, (lat, lon), country, admin1 id, city name (None: don't check)
GOLDEN = [
    ("CN Tower", (43.6426, -79.3871), "CA", "iso:CA-ON", "Toronto"),
    ("Lake Louise", (51.4254, -116.1773), "CA", "iso:CA-AB", None),
    ("Yosemite Valley", (37.7456, -119.5936), "US", "iso:US-CA", None),
    ("Las Vegas Strip", (36.1147, -115.1728), "US", "iso:US-NV", None),
    ("Bengaluru MG Road", (12.9756, 77.6060), "IN", "iso:IN-KA", "Bengaluru"),
    ("Gateway of India", (18.9220, 72.8347), "IN", "iso:IN-MH", "Mumbai"),
    ("Golden Gate Bridge", (37.8199, -122.4783), "US", "iso:US-CA", None),
]


@pytest.mark.parametrize(("name", "point", "cc", "admin1", "city"), GOLDEN, ids=[g[0] for g in GOLDEN])
def test_golden(geo, name, point, cc, admin1, city):
    r = geo.lookup(*point)
    assert r.cc == cc
    assert r.admin1 is not None and r.admin1.id == admin1
    assert r.sources["country"] in ("world/countries:polygon", "world/countries:offshore")
    if city is not None:
        assert r.city is not None and r.city.name == city
    if r.city is not None:
        assert r.city.codes["country"] == cc  # never a city across the border
    assert r.data_version == "world-2026.11"
    assert r.label.endswith(r.country.name)


def test_cn_tower_details(geo):
    r = geo.lookup(43.6426, -79.3871)
    assert r.label == "Toronto, Ontario, Canada"
    assert r.country.id == "iso:CA" and r.country.codes["iso2"] == "CA"
    assert r.city.id.startswith("geonames:")
    assert r.tz == "America/Toronto"


def test_bengaluru_tz(geo):
    assert geo.lookup(12.9756, 77.6060).tz == "Asia/Kolkata"


def test_niagara_falls_stays_on_its_side(geo):
    r = geo.lookup(43.0828, -79.0742)
    assert r.cc in ("US", "CA")
    assert r.city.name == "Niagara Falls"
    assert r.city.codes["country"] == r.cc


def test_mid_pacific_has_no_country(geo):
    r = geo.lookup(20.0, -140.0)
    assert r.country is None and r.admin1 is None and r.city is None
    assert r.label.startswith("Offshore")


def test_sevastopol_reports_the_data_and_fills_disputed(geo):
    r = geo.lookup(44.6167, 33.5254)
    # Natural Earth's 1:10m coast misses this point; the country comes from territorial waters
    assert r.sources["country"] == "world/countries:offshore"
    assert r.cc == "RU"  # Natural Earth's default (de facto) polygon
    assert r.admin1.id == "iso:UA-40"  # its admin-1 code
    assert r.city.name == "Sevastopol"
    d = r.disputed
    assert d is not None
    assert d.claimants == ("RU", "UA") and d.administered_by == "RU"
    assert d.applied_view == "de_facto"


def test_lookup_many_matches_lookup_on_real_points(geo):
    rng = np.random.default_rng(7)
    lat = np.degrees(np.arcsin(rng.uniform(-1, 1, 400)))
    lon = rng.uniform(-180, 180, 400)
    lat = np.concatenate([lat, [g[1][0] for g in GOLDEN], [44.6167, 43.0828]])
    lon = np.concatenate([lon, [g[1][1] for g in GOLDEN], [33.5254, -79.0742]])
    for r, a, b in zip(geo.lookup_many(lat, lon), lat, lon, strict=True):
        assert r.to_dict() == geo.lookup(float(a), float(b)).to_dict()
