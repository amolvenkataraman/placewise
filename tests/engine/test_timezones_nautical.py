"""Nautical time zones by longitude (placewise.engine._timezones.nautical), and Result.tz beyond
every territorial sea (the synthetic world of lookup_kit)."""

from datetime import datetime

import numpy as np
import pytest
from lookup_kit import write_world

from placewise.constants import lookup as const
from placewise.engine import Geocoder
from placewise.engine._timezones import nautical


def test_bands_are_centred_on_multiples_of_15_degrees():
    lon = np.array([0.0, 7.4, 7.5, 22.4, -7.4, -7.6, 150.0, -150.0, 172.4, 172.5, 180.0, -172.5, -180.0])
    assert nautical.offsets(lon).tolist() == [0, 0, 1, 1, 0, -1, 10, -10, 11, 12, 12, -11, -12]


def test_tzdb_names_invert_the_sign():
    assert nautical.zone_names([0.0, 150.0, -150.0, 179.9, -179.9]) == [
        "Etc/GMT", "Etc/GMT-10", "Etc/GMT+10", "Etc/GMT-12", "Etc/GMT+12",
    ]  # fmt: skip


def test_every_name_is_a_real_zone():
    zoneinfo = pytest.importorskip("zoneinfo")
    for hours in range(-12, 13):
        try:
            zone = zoneinfo.ZoneInfo(nautical.name(hours))
        except zoneinfo.ZoneInfoNotFoundError:  # no tz database on this system
            pytest.skip("no tz database")
        assert zone.utcoffset(datetime(2026, 1, 1)).total_seconds() == hours * 3600


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    return Geocoder(packs=[write_world(tmp_path_factory.mktemp("nautical"))])


def test_far_offshore_the_zone_is_nautical(geo):
    r = geo.lookup(-10.0, -160.0)  # no country within 200 nmi
    assert r.country is None and r.tz == "Etc/GMT+11" and r.sources["tz"] == const.TZ_NAUTICAL


def test_territorial_sea_keeps_the_country_zone(geo):
    r = geo.lookup(1.1, -139.5)  # 11 km off Alphaland
    assert r.tz == "Pacific/Alpha" and r.sources["tz"] != const.TZ_NAUTICAL


def test_batch_mixes_land_and_sea(geo):
    rs = geo.lookup_many([0.75, -10.0, 30.0], [-139.5, -160.0, 100.5])
    assert [r.tz for r in rs] == ["Pacific/Alpha", "Etc/GMT+11", "Etc/GMT-7"]
