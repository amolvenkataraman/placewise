"""Privacy zones: cut tracks near sensitive places without leaving the cut on a guessable circle."""

import numpy as np
import pytest
from privacy_kit import HOME, KEY, OTHER_KEY, RIDE_META, along_path_m, distance_m, same_track, straight
from privacy_kit import street_route as route

from placewise.model import Point, PrivacyZone
from placewise.privacy.location import apply_zones, zone_extra_m
from placewise.tracks import Track

ZONE = PrivacyZone("home", Point(*HOME), 200.0)


def _key_with_extra_above(zone, fraction):
    # the extra is secret and uniform in [0, radius); pick a key whose extra is large enough that
    # the spread test measures the mechanism, not a lucky near-zero draw
    for i in range(200):
        key = f"zone-test-key-{i:04d}".encode() * 2
        if zone_extra_m(zone, key) > fraction * zone.radius_m:
            return key
    raise AssertionError("no key found")


def test_extra_is_keyed_per_zone_and_within_the_radius():
    extra = zone_extra_m(ZONE, KEY)
    assert 0 <= extra < ZONE.radius_m
    assert zone_extra_m(ZONE, KEY) == extra  # deterministic
    assert zone_extra_m(ZONE, OTHER_KEY) != extra
    assert zone_extra_m(PrivacyZone("work", Point(*HOME), 200.0), KEY) != extra
    extras = [zone_extra_m(ZONE, f"key-{i:02d}".encode() * 4) for i in range(200)]
    assert min(extras) < 0.2 * ZONE.radius_m and max(extras) > 0.8 * ZONE.radius_m  # spans the range


def test_no_point_within_the_radius_survives():
    rng = np.random.default_rng(1)
    for bearing in range(0, 360, 30):
        out = apply_zones(route(bearing, rng), [ZONE], KEY)
        assert len(out) > 0
        assert np.all(distance_m(out.lat, out.lon, HOME) > ZONE.radius_m)


def test_cut_extends_the_secret_extra_along_the_path():
    rng = np.random.default_rng(2)
    track = route(45, rng)
    out = apply_zones(track, [ZONE], KEY)
    s = along_path_m(track)
    last_inside = s[distance_m(track.lat, track.lon, HOME) <= ZONE.radius_m].max()
    first_kept = int(np.flatnonzero(track.time == out.time[0])[0])
    assert s[first_kept] - last_inside > zone_extra_m(ZONE, KEY)
    assert s[first_kept - 1] - last_inside <= zone_extra_m(ZONE, KEY)  # and no more than that


def test_cut_points_do_not_lie_on_a_common_circle():
    key = _key_with_extra_above(ZONE, 0.5)
    rng = np.random.default_rng(3)
    tracks = [route(bearing, rng) for bearing in np.linspace(0, 360, 24, endpoint=False)]
    cut = np.array(
        [distance_m(t.lat[0], t.lon[0], HOME) for t in (apply_zones(t, [ZONE], key) for t in tracks)]
    )
    # what a plain cut at the circle's edge would leave: every endpoint at ~ the radius
    naive = np.array(
        [distance_m(t.lat, t.lon, HOME)[distance_m(t.lat, t.lon, HOME) > ZONE.radius_m][0] for t in tracks]
    )
    assert naive.std() < 3.0  # sanity: the naive cut really does draw the circle
    assert cut.std() > 10.0
    assert cut.std() > 5 * naive.std()
    assert cut.min() > ZONE.radius_m


def test_passing_through_a_zone_splits_the_segment():
    west = (HOME[0], HOME[1] - 0.01)
    east = (HOME[0], HOME[1] + 0.01)
    track = straight(west, east, 401)  # ~2.2 km, through the centre
    out = apply_zones(track, [ZONE], KEY)
    assert track.segments == (0,)
    assert len(out.segments) == 2
    first, second = out.iter_segments()
    assert first.lon.max() < HOME[1] < second.lon.min()


def test_several_zones_and_whole_segments_inside():
    other = PrivacyZone("work", Point(HOME[0], HOME[1] + 0.02), 150.0)
    a = straight((HOME[0], HOME[1] - 0.01), (HOME[0], HOME[1] + 0.03), 801)
    inside = straight((HOME[0], HOME[1] - 0.0005), (HOME[0], HOME[1] + 0.0005), 11, t0=a.time[-1] + 60)
    track = Track(
        time=np.r_[a.time, inside.time],
        lat=np.r_[a.lat, inside.lat],
        lon=np.r_[a.lon, inside.lon],
        segments=(0, len(a)),
    )
    out = apply_zones(track, [ZONE, other], KEY)
    assert len(out.segments) == 3  # the first segment cut twice; the second wholly removed
    for zone in (ZONE, other):
        assert np.all(distance_m(out.lat, out.lon, (zone.point.lat, zone.point.lon)) > zone.radius_m)


def test_deterministic_and_key_separated():
    rng = np.random.default_rng(4)
    tracks = [route(b, rng, meta=RIDE_META) for b in range(0, 360, 45)]
    first = [apply_zones(t, [ZONE], KEY) for t in tracks]
    again = [apply_zones(t, [ZONE], KEY) for t in tracks]
    other = [apply_zones(t, [ZONE], OTHER_KEY) for t in tracks]
    assert all(same_track(a, b) for a, b in zip(first, again, strict=True))
    assert not all(same_track(a, b) for a, b in zip(first, other, strict=True))
    assert first[0].meta == RIDE_META  # zones don't touch metadata; policies decide that


def test_optional_columns_follow_and_no_zones_is_identity():
    rng = np.random.default_rng(5)
    base = route(10, rng)
    track = Track.from_columns({**{c: getattr(base, c) for c in base.columns}, "hr": np.arange(len(base))})
    out = apply_zones(track, [ZONE], KEY)
    assert out.hr is not None and np.array_equal(out.hr, track.hr[np.isin(track.time, out.time)])
    assert same_track(apply_zones(track, [], KEY), track)
    empty = Track(time=[], lat=[], lon=[])
    assert len(apply_zones(empty, [ZONE], KEY)) == 0


@pytest.mark.parametrize("key", [b"", b"short", "a text key of enough length"])
def test_rejects_weak_or_non_bytes_keys(key):
    with pytest.raises((ValueError, TypeError)):
        apply_zones(straight(HOME, (0.01, -20.0), 10), [ZONE], key)
