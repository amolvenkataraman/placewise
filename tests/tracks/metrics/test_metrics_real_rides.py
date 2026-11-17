"""Realism check: clean and measure on real 1 Hz bus rides (tests/data/tracks, anonymised, CC BY 4.0)."""

import re
from pathlib import Path

import numpy as np
import pytest

from placewise.tracks import Track
from placewise.tracks.cleaning import remove_spikes, smooth
from placewise.tracks.metrics import stats

DATA = Path(__file__).parents[2] / "data" / "tracks"
# distance (km) from the fixtures' README
FIXTURES = {
    "ttc_900_airport_express.gpx": 10.4,
    "yrt_viva_purple.gpx": 4.9,
    "hyderabad_airport_express.gpx": 22.5,
    "hyderabad_bengaluru_highway.gpx": 37.5,
}
_TRKPT = re.compile(
    r'<trkpt lat="([^"]+)" lon="([^"]+)"><ele>([^<]+)</ele><time>([^<]+)</time><speed>([^<]+)</speed>'
)


def read_fixture(name):
    """Just enough GPX 1.0 for these files, so this test doesn't depend on the GPX reader."""
    rows = _TRKPT.findall((DATA / name).read_text())
    lat, lon, ele, time, speed = zip(*rows, strict=True)
    seconds = np.array([s.rstrip("Z") for s in time], dtype="datetime64[s]").astype(np.int64).astype(float)
    return Track(seconds, lat, lon, ele=ele, speed=speed)


@pytest.mark.parametrize(("name", "km"), FIXTURES.items())
def test_real_rides(name, km):
    track = read_fixture(name)
    s = stats(track)
    assert s.distance_km == pytest.approx(km, rel=0.02)
    assert s.moving_time_s + s.stopped_time_s == s.duration_s  # one segment: no gap time
    assert 0.5 * s.duration_s < s.moving_time_s <= s.duration_s
    assert s.max_speed_kmh < 130  # buses, by the device's own speed column
    for cleaned in (remove_spikes(track), smooth(track)):
        assert stats(cleaned).distance_km == pytest.approx(s.distance_km, rel=0.03)
