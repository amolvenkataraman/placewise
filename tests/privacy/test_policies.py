"""Applying a PrivacyPolicy in its fixed order, and the shipped presets."""

import numpy as np
import pytest
from privacy_kit import HOME, KEY, OTHER_KEY, RIDE_META, distance_m, same_track
from privacy_kit import street_route as route

from placewise.constants import privacy as constants
from placewise.model import Point, PrivacyPolicy, PrivacyZone
from placewise.privacy import policies, presets
from placewise.privacy.location import apply_zones, geo_indistinguishable, keyed_snap, trim_ends
from placewise.privacy.time import coarsen_times
from placewise.tracks import Track, TrackMeta

ZONE = PrivacyZone("home", Point(*HOME), 200.0)


def _ride():
    base = route(30, np.random.default_rng(11), length_m=3000.0, meta=RIDE_META)
    n = len(base)
    return Track.from_columns(
        {
            **{c: getattr(base, c) for c in base.columns},
            "speed": np.full(n, 2.5),
            "heading": np.full(n, 30.0),
            "hr": np.full(n, 140.0),
        },
        meta=RIDE_META,
    )


def test_steps_run_in_the_documented_order():
    ride = _ride()
    policy = PrivacyPolicy(zones=(ZONE,), trim_m=100, trim_jitter_m=50, snap_m=50, time_resolution="minute")
    out = policies.apply(ride, policy, KEY)
    expected = coarsen_times(trim_ends(apply_zones(ride, [ZONE], KEY), 100, 50, KEY), "minute")
    lat, lon = keyed_snap(expected.lat, expected.lon, 50, KEY)
    assert np.array_equal(out.lat, lat) and np.array_equal(out.lon, lon)
    assert np.array_equal(out.time, expected.time) and out.segments == expected.segments
    assert np.all(distance_m(out.lat, out.lon, HOME) > ZONE.radius_m - 50)  # snapping moves ≤ ~35 m


def test_noise_step_and_columns_that_would_undo_it():
    ride = _ride()
    out = policies.apply(ride, PrivacyPolicy(noise_epsilon=0.01), KEY)
    lat, lon = geo_indistinguishable(ride.lat, ride.lon, 0.01, KEY)
    assert np.array_equal(out.lat, lat) and np.array_equal(out.lon, lon)
    # dead reckoning from speed and heading would rebuild the exact path, so they go
    assert out.speed is None and out.heading is None
    assert np.array_equal(out.hr, ride.hr)


def test_metadata_is_stripped_unless_asked_to_keep_it():
    ride = _ride()
    assert policies.apply(ride, PrivacyPolicy(), KEY).meta == TrackMeta(activity="cycling")
    kept = policies.apply(ride, PrivacyPolicy(strip_metadata=False), KEY)
    assert same_track(kept, ride)


def test_snap_and_noise_together_is_ambiguous():
    with pytest.raises(ValueError, match="snap"):
        policies.apply(_ride(), PrivacyPolicy(snap_m=50, noise_epsilon=0.01), KEY)


def test_population_cloaking_waits_for_the_geocoder():
    with pytest.raises(NotImplementedError, match="geocoder"):
        policies.apply(_ride(), PrivacyPolicy(cloak_min_population=1000), KEY)


def test_deterministic_and_key_separated():
    ride = _ride()
    policy = presets.preset("public_share", zones=(ZONE,))
    assert same_track(policies.apply(ride, policy, KEY), policies.apply(ride, policy, KEY))
    assert not same_track(policies.apply(ride, policy, KEY), policies.apply(ride, policy, OTHER_KEY))


def test_presets_use_the_documented_constants():
    assert presets.NAMES == ("public_share", "friends", "research")
    for name in presets.NAMES:
        policy = presets.preset(name)
        numbers = constants.PRESETS[name]
        assert isinstance(policy, PrivacyPolicy) and policy.zones == ()
        for field, value in numbers.items():
            assert getattr(policy, field) == value
        assert policy.strip_metadata
    with_zone = presets.preset("friends", zones=[ZONE])
    assert with_zone.zones == (ZONE,)
    with pytest.raises(ValueError, match="public_share"):
        presets.preset("everyone")


def test_presets_run_end_to_end():
    ride = _ride()
    for name in presets.NAMES:
        policy = presets.preset(name, zones=(ZONE,))
        out = policies.apply(ride, policy, KEY)
        assert 0 < len(out) < len(ride)
        if policy.noise_epsilon is None:  # noise may legitimately move a point back towards the zone
            assert np.all(distance_m(out.lat, out.lon, HOME) > 100)
