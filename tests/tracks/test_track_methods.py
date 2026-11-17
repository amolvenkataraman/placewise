"""Track's convenience methods: each one is the module function it delegates to.

The synthetic day sits in open ocean near 0°N 20°W: a 15-minute stay, 20 minutes heading east,
another stay, with a little jitter, a spike, a duplicate fix and a gap for clean() to deal with.
"""

import numpy as np
import pytest
from numpy.testing import assert_array_equal

from placewise import io
from placewise.model import Feature, Outline
from placewise.tracks import Track, TrackMeta, _ops, clean, combine, interpolate, measure, segment, spatial

T0 = 1.7e9  # 2023-11-14, so drop_invalid's "not in the future" check passes


def _day():
    rng = np.random.default_rng(3)
    t = np.arange(0, 3600, 10.0)
    lon = -20.0 + np.clip(t - 900, 0, 1200) * 5 / 111_195  # 5 m/s east between the stays
    lat = rng.normal(0, 2e-5, len(t))
    lat[150] += 0.01  # a 1 km spike
    keep = (t < 2400) | (t > 2700)  # a five-minute silence
    t, lat, lon = t[keep], lat[keep], lon[keep]
    t, lat, lon = np.r_[t, t[5]], np.r_[lat, lat[5]], np.r_[lon, lon[5]]  # a duplicate, out of order
    n = len(t)
    return Track(
        T0 + t,
        lat,
        lon,
        segments=(0, 200),
        meta=TrackMeta(name="day", activity="walking"),
        ele=10 + rng.normal(0, 1, n),
        hr=np.full(n, 110.0),
        heading=np.full(n, 90.0),
    )


def _same(a, b):
    assert a.columns == b.columns
    for name in a.columns:
        assert_array_equal(getattr(a, name), getattr(b, name))
    assert a.segments == b.segments
    assert a.meta == b.meta


@pytest.fixture
def day():
    return _day()


@pytest.fixture
def tidy():
    return clean.sort_and_dedupe(_day())


def _square(west, east, south=-0.01, north=0.01):
    return Outline((((south, west), (south, east), (north, east), (north, west)),))


def test_measure_methods(tidy):
    assert tidy.stats() == measure.stats(tidy)
    assert tidy.splits(every_km=2.0) == measure.splits(tidy, every_km=2.0)


def test_clean_is_the_default_pipeline(day):
    expected = clean.split_gaps(clean.remove_spikes(clean.drop_invalid(clean.sort_and_dedupe(day))))
    _same(day.clean(), expected)
    assert len(day.clean()) == len(day) - 2  # the duplicate and the spike


def test_clean_methods(tidy):
    _same(tidy.smooth(), clean.smooth(tidy))
    _same(tidy.thin(every_s=60), clean.thin(tidy, every_s=60))


def test_interpolate_methods(tidy):
    times = T0 + np.array([5.0, 1000.0, 5000.0])
    for got, want in zip(tidy.position_at(times), interpolate.position_at(tidy, times), strict=True):
        assert_array_equal(got, want)
    _same(tidy.resample(every_s=30), interpolate.resample(tidy, every_s=30))


def test_segment_methods(tidy):
    assert tidy.stays() == segment.stays(tidy)
    assert len(tidy.stays()) == 2
    assert tidy.trips() == segment.trips(tidy, segment.stays(tidy))
    assert tidy.trips(tidy.stays(radius_m=50)) == segment.trips(tidy, segment.stays(tidy, radius_m=50))


def test_spatial_methods(tidy):
    square = _square(-19.99, -19.98)
    assert tidy.time_inside(square) == spatial.time_inside(tidy, square)
    features = [Feature(outlines=(_square(-20.1, -19.99),)), Feature(outlines=(_square(-19.99, -19.9),))]
    assert tidy.crossings(features) == spatial.crossings(tidy, features)
    assert tidy.closest_pass(0.001, -19.97) == spatial.closest_pass(tidy, 0.001, -19.97)
    assert tidy.bbox == spatial.bbox(tidy)


def test_structure_methods(tidy):
    new_ele = np.zeros(len(tidy))
    _same(tidy.replace(ele=new_ele), _ops.replace(tidy, ele=new_ele))
    assert_array_equal(tidy.replace(ele=new_ele).ele, new_ele)
    assert tidy.replace(hr=None).hr is None  # None drops an optional column
    assert tidy.segment_bounds() == _ops.bounds(tidy)
    _same(tidy.crop(T0 + 100, T0 + 900), combine.crop(tidy, T0 + 100, T0 + 900))
    for got, want in zip(
        tidy.split(by="gap", max_gap_s=60), combine.split(tidy, by="gap", max_gap_s=60), strict=True
    ):
        _same(got, want)
    _same(tidy.reverse(), combine.reverse(tidy))


def test_io_methods(tidy, tmp_path):
    path = tmp_path / "day.gpx"
    text = tidy.to_gpx(path)
    assert text == io.write_gpx(tidy, None)
    assert path.read_text() == text
    assert tidy.to_geojson() == io.write_geojson_track(tidy)
    _same(Track.read(path), io.read_track(path)[0][0])
    _same(Track.read(path.read_bytes()), io.read_track(path.read_bytes())[0][0])
