"""Result.tz from the world pack's timezones polygons, on both sides of zone lines: public places
only. Skipped when the world pack isn't built, or was built before the timezones layer."""

import pytest
from e2e_kit import geocoder, require_packs

from placewise.packs import open_pack

POINTS = [
    ("Indianapolis", (39.7684, -86.1581), "America/Indiana/Indianapolis"),
    ("Gary, Indiana", (41.5934, -87.3464), "America/Chicago"),
    ("Phoenix", (33.4484, -112.0740), "America/Phoenix"),
    ("Window Rock (Navajo Nation)", (35.6806, -109.0526), "America/Denver"),
    ("Regina", (50.4452, -104.6189), "America/Regina"),
    ("El Paso", (31.7619, -106.4850), "America/Denver"),
    ("Pensacola", (30.4213, -87.2169), "America/Chicago"),
    ("Tallahassee", (30.4383, -84.2807), "America/New_York"),
    ("Kalgoorlie", (-30.7490, 121.4660), "Australia/Perth"),
    ("Eucla", (-31.6770, 128.8890), "Australia/Eucla"),
    ("Vladivostok", (43.1155, 131.8855), "Asia/Vladivostok"),
    ("Manaus", (-3.1190, -60.0217), "America/Manaus"),
    ("Belém", (-1.4558, -48.4902), "America/Belem"),
    ("Eirunepé", (-6.6603, -69.8739), "America/Eirunepe"),
    ("Leh (India-administered)", (34.1526, 77.5771), "Asia/Kolkata"),
    ("Kashgar", (39.4700, 75.9900), "Asia/Urumqi"),
]


@pytest.fixture(scope="module")
def geo():
    (path,) = require_packs("world")
    if "timezones" not in open_pack(path):
        pytest.skip(f"{path.name} was built before the timezones layer")
    return geocoder("world")


@pytest.mark.parametrize(("name", "point", "zone"), POINTS, ids=[p[0] for p in POINTS])
def test_zone_on_each_side_of_a_line(geo, name, point, zone):
    r = geo.lookup(*point)
    assert r.tz == zone
    assert r.sources["tz"].startswith("world/timezones:")


def test_open_ocean_has_no_zone(geo):
    assert geo.lookup(0.0, -140.0).tz is None
