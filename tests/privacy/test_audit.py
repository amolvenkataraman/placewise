"""The pre-share audit: what an observer could infer (home, work, repeated endpoints)."""

import numpy as np
import pytest
from privacy_synth import HOME, T0, WORK, distance_m, straight

from placewise.privacy.audit import AuditReport, Finding, audit
from placewise.tracks import Track

UTC_OFFSET_H = -1.0  # roughly local solar time at 20°W
HOUR = 3600.0


def _stay(place, local_start_h, hours, day, rng, every_s=600.0):
    """Points every 10 minutes at `place`, with ~10 m of GPS scatter."""
    t0 = T0 + day * 86400 + (local_start_h - UTC_OFFSET_H) * HOUR
    n = int(hours * HOUR / every_s)
    scatter = rng.normal(0, 10 / 111_195, (2, n))
    return Track(time=t0 + np.arange(n) * every_s, lat=place[0] + scatter[0], lon=place[1] + scatter[1])


def _commute(a, b, local_start_h, day):
    t0 = T0 + day * 86400 + (local_start_h - UTC_OFFSET_H) * HOUR
    return straight(a, b, 81, t0=t0, dt=30.0)  # ~6 km in 40 minutes


def _fortnight(days=14):
    rng = np.random.default_rng(7)
    tracks = []
    for day in range(days):  # day 0 is a Monday
        tracks.append(_stay(HOME, 0, 7.5, day, rng))  # asleep 00:00-07:30 local
        if day % 7 < 5:
            tracks.append(_commute(HOME, WORK, 8, day))
            tracks.append(_stay(WORK, 9, 8, day, rng))
            tracks.append(_commute(WORK, HOME, 17.5, day))
    return tracks


def test_finds_home_work_and_repeated_endpoints():
    report = audit(_fortnight(), utc_offset_h=UTC_OFFSET_H)
    assert isinstance(report, AuditReport)
    home, work = report.home, report.work
    assert isinstance(home, Finding) and home.kind == "home"
    assert distance_m(home.point.lat, home.point.lon, HOME) < 15
    assert 5 < home.precision_m < 40  # the ~10 m scatter, not the cell size
    assert home.evidence == 14  # nights
    assert home.points > 14 * 30
    assert home.severity == "high"
    assert work.kind == "work" and distance_m(work.point.lat, work.point.lon, WORK) < 15
    assert work.evidence == 10  # weekdays
    assert work.severity == "high"
    near = [min(distance_m(f.point.lat, f.point.lon, p) for p in (HOME, WORK)) for f in report.endpoints]
    assert len(report.endpoints) == 2 and max(near) < 30
    assert all(f.kind == "endpoint" and f.evidence >= 20 for f in report.endpoints)
    assert report.findings == (home, work, *report.endpoints)


def test_utc_offset_decides_what_counts_as_night():
    # read as UTC+11, the working day falls in "local" 00-06, so home lands at the office
    report = audit(_fortnight(), utc_offset_h=11.0)
    assert distance_m(report.home.point.lat, report.home.point.lon, WORK) < 15


def test_moving_points_are_not_stationary_evidence():
    tracks = [_commute(HOME, WORK, 1, day) for day in range(5)]  # driving at night, never stopping
    report = audit(tracks, utc_offset_h=UTC_OFFSET_H)
    assert report.home is None


def test_severity_grows_with_evidence():
    rng = np.random.default_rng(8)
    one_night = audit([_stay(HOME, 0, 6, 0, rng)], utc_offset_h=UTC_OFFSET_H)
    assert one_night.home.evidence == 1 and one_night.home.severity == "low"
    assert (
        audit([_stay(HOME, 0, 6, d, rng) for d in range(4)], utc_offset_h=UTC_OFFSET_H).home.severity
        == "medium"
    )


def test_points_tuple_and_empty_input():
    tracks = _fortnight(7)
    merged = (
        np.concatenate([t.time for t in tracks]),
        np.concatenate([t.lat for t in tracks]),
        np.concatenate([t.lon for t in tracks]),
    )
    report = audit(merged, utc_offset_h=UTC_OFFSET_H)
    assert distance_m(report.home.point.lat, report.home.point.lon, HOME) < 15
    assert report.endpoints == ()  # one bag of points: no segments, so no endpoints to repeat
    empty = audit(Track(time=[], lat=[], lon=[]))
    assert empty.home is None and empty.work is None and empty.endpoints == () and empty.findings == ()


def test_findings_are_frozen_and_serialisable():
    report = audit(_fortnight(7), utc_offset_h=UTC_OFFSET_H)
    with pytest.raises(AttributeError):
        report.home.severity = "low"
    assert report.home.to_dict()["kind"] == "home"


def test_a_tuple_of_three_tracks_is_tracks_not_points():
    tracks = tuple(_fortnight(1)[:3])
    assert len(tracks) == 3
    assert audit(tracks, utc_offset_h=UTC_OFFSET_H).endpoints != ()
