"""Stays, trips, travel modes and flights on synthetic tracks in open ocean near 0°N 20°W."""

import numpy as np
import pytest

from placewise.geo import destination, haversine
from placewise.tracks import Track
from placewise.tracks.segment import Flight, Stay, flights, mode_runs, stays, travel_mode, trips

T0 = 1.8e9
M_PER_DEG = 111_195.08  # metres per degree of longitude on the equator (mean radius)


def _concat(*parts, segments=None):
    t, lat, lon = (np.concatenate([p[k] for p in parts]) for k in range(3))
    return Track(time=t, lat=lat, lon=lon, segments=segments)


def _still(t0, duration_s, lat, lon, step_s=60, jitter_m=5.0, seed=0):
    n = int(duration_s // step_s) + 1
    rng = np.random.default_rng(seed)
    dlat, dlon = rng.uniform(-jitter_m, jitter_m, (2, n)) / M_PER_DEG
    return T0 + t0 + np.arange(n) * step_s, lat + dlat, lon + dlon


def _move_east(t0, duration_s, lon0, speed_kmh, step_s=10, lat=0.0):
    n = int(duration_s // step_s)
    t = np.arange(1, n + 1) * step_s
    return T0 + t0 + t, np.full(n, lat), lon0 + speed_kmh / 3.6 * t / M_PER_DEG


def _two_stays():
    """Stay 30 min, walk 3 km east at 200 m a minute, stay 40 min."""
    lon_a, lon_b = -20.0, -20.0 + 3000 / M_PER_DEG
    a = _still(0, 1800, 0.0, lon_a, seed=1)
    k = np.arange(1, 15)
    move = (T0 + 1800 + 60 * k, np.zeros(14), lon_a + 200 * k / M_PER_DEG)
    b = _still(1800 + 900, 2400, 0.0, lon_b, seed=2)
    return _concat(a, move, b), lon_a, lon_b


def test_two_stays_with_movement_between():
    track, lon_a, lon_b = _two_stays()
    found = stays(track)
    assert len(found) == 2
    a, b = found
    assert isinstance(a, Stay)
    assert (a.start, a.end, a.n_points, a.first_index, a.last_index) == (T0, T0 + 1800, 31, 0, 30)
    assert (b.start, b.end, b.n_points) == (T0 + 2700, T0 + 5100, 41)
    assert a.duration_s == 1800
    assert haversine(a.lat, a.lon, 0.0, lon_a) < 0.01  # centre within 10 m
    assert haversine(b.lat, b.lon, 0.0, lon_b) < 0.01

    (trip,) = trips(track, found)
    assert (trip.start, trip.end) == (a.end, b.start)
    assert (trip.first_index, trip.last_index, trip.n_points) == (30, 45, 16)
    assert trip.origin == a and trip.destination == b
    assert trip.distance_km == pytest.approx(3.0, abs=0.02)


def test_a_quiet_phone_that_did_not_move_is_bridged():
    p = (0.0, -20.0)
    before = _still(0, 300, *p, seed=3)  # 5 min each side: too short on their own
    after = _still(300 + 3 * 3600, 300, *p, seed=4)
    track = _concat(before, after)
    (stay,) = stays(track)
    assert (stay.start, stay.end, stay.n_points) == (T0, T0 + 300 + 3 * 3600 + 300, 12)
    assert stays(track, max_bridge_s=3600) == []

    # the same silence across a segment break is bridged too
    split = _concat(before, after, segments=(0, 6))
    assert len(stays(split)) == 1

    moved = _concat(before, _still(300 + 3 * 3600, 300, 0.0, -19.95, seed=4))
    assert stays(moved) == []


def _reference_stays(track, radius_m, min_duration_s, max_bridge_s):
    """The textbook anchor-point algorithm, one point at a time."""
    t, lat, lon = track.time, track.lat, track.lon
    n, i, spans = len(track), 0, []
    while i < n:
        j = i + 1
        while (
            j < n
            and haversine(lat[i], lon[i], lat[j], lon[j]) * 1000 <= radius_m
            and t[j] - t[j - 1] <= (max_bridge_s)
        ):
            j += 1
        if t[j - 1] - t[i] >= min_duration_s:
            spans.append((i, j - 1))
            i = j
        else:
            i += 1
    return spans


def test_stays_match_the_reference_algorithm_on_a_random_walk():
    rng = np.random.default_rng(11)
    n = 3000
    # bursts of motion between pauses, with occasional silences
    speed = np.where(rng.random(n) < 0.6, 0.0, rng.uniform(0, 40, n))
    dt = np.where(rng.random(n) < 0.01, rng.uniform(600, 9000, n), rng.uniform(5, 90, n))
    heading = np.cumsum(rng.normal(0, 0.6, n))
    step = speed * dt / M_PER_DEG * 0.05 + rng.normal(0, 8, n) / M_PER_DEG
    track = Track(
        time=T0 + np.cumsum(dt),
        lat=np.cumsum(step * np.cos(heading)),
        lon=-20 + np.cumsum(step * np.sin(heading)),
    )
    for radius, minimum, bridge in [(100, 600, 86400), (50, 300, 3600), (200, 1200, 1e9)]:
        found = [(s.first_index, s.last_index) for s in stays(track, radius, minimum, bridge)]
        assert found == _reference_stays(track, radius, minimum, bridge)
        assert found  # the walk does pause


def _walk_then_drive():
    walk = _move_east(0, 600, -20.0, 5)
    drive = _move_east(600, 600, walk[2][-1], 60)
    start = (np.array([T0]), np.zeros(1), np.array([-20.0]))
    return _concat(start, walk, drive)


def test_mode_switches_from_walk_to_drive():
    track = _walk_then_drive()
    modes = travel_mode(track)
    assert modes.shape == (len(track) - 1,)
    mid = (track.time[:-1] + track.time[1:]) / 2 - T0
    assert set(modes[mid < 600 - 120]) == {"walk"}
    assert set(modes[mid > 600 + 120]) == {"drive"}
    runs = mode_runs(track)
    assert [r.mode for r in runs] == ["walk", "drive"]
    assert runs[0].start == T0 and runs[-1].end == track.time[-1]
    assert abs(runs[1].start - (T0 + 600)) <= 60


def test_bike_gap_and_segment_break():
    bike = _move_east(0, 600, -20.0, 15)
    later = _move_east(600 + 3 * 3600, 600, bike[2][-1], 15)
    track = _concat(bike, later)
    modes = travel_mode(track)
    gap_step = len(bike[0]) - 1
    assert modes[gap_step] == "gap"
    assert set(np.delete(modes, gap_step)) == {"bike"}

    split = _concat(_move_east(0, 600, -20.0, 15), _move_east(610, 600, bike[2][-1], 15), segments=(0, 60))
    assert travel_mode(split)[59] == "gap"


def test_airborne_needs_speed_on_both_sides_so_a_spike_is_not_a_flight():
    drive = _move_east(0, 1200, -20.0, 80)
    lon = drive[2].copy()
    lon[60] += 0.5  # a 55 km GPS spike for one fix
    modes = travel_mode(Track(time=drive[0], lat=drive[1], lon=lon))
    assert "flight" not in set(modes)

    cruise = _move_east(0, 3600, -20.0, 850, step_s=30)
    modes = travel_mode(Track(time=cruise[0], lat=cruise[1], lon=cruise[2]))
    assert set(modes) == {"flight"}


def test_airborne_run_is_a_flight():
    taxi = _move_east(0, 600, -20.0, 20, step_s=30)
    air = _move_east(600, 3600, taxi[2][-1], 850, step_s=30)
    land = _move_east(4200, 600, air[2][-1], 20, step_s=30)
    track = _concat(taxi, air, land)
    (flight,) = flights(track)
    assert isinstance(flight, Flight)
    assert flight.kind == "airborne"
    assert T0 + 600 <= flight.start <= T0 + 600 + 180
    assert T0 + 4200 - 180 <= flight.end <= T0 + 4200
    assert flight.distance_km == pytest.approx(
        haversine(flight.from_lat, flight.from_lon, flight.to_lat, flight.to_lon)
    )


def test_silent_jumps_are_flights():
    here = _still(0, 600, 0.0, -20.0)
    far_lat, far_lon = destination(0.0, -20.0, 90, 3100)
    away = _still(5 * 86400, 600, far_lat, far_lon)  # 3100 km, five days later
    (flight,) = flights(_concat(here, away))
    assert flight.kind == "silent"
    assert (flight.start, flight.end) == (here[0][-1], away[0][0])
    assert (flight.first_index, flight.last_index) == (10, 11)
    assert flight.distance_km == pytest.approx(3100, rel=1e-3)

    near_lat, near_lon = destination(0.0, -20.0, 90, 900)
    assert len(flights(_concat(here, _still(86400, 600, near_lat, near_lon)))) == 1  # 900 km in a day
    assert flights(_concat(here, _still(3 * 86400, 600, near_lat, near_lon))) == []  # 900 km in 3 days
