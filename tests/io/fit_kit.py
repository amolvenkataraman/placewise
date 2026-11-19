"""FIT fixtures for the reader tests: an activity written by the spec-following encoder in
fit_writer.py, round the Serpentine in Hyde Park unless other points are given, and fitdecode (an
independent MIT decoder) as the oracle placewise must agree with, field by field. Every
coordinate is a public place or open ocean."""

import io
from datetime import datetime, timezone

import fitdecode
import numpy as np
import pytest
from fit_writer import (
    MESG_DEVICE_INFO,
    MESG_EVENT,
    MESG_FILE_ID,
    MESG_LAP,
    MESG_RECORD,
    MESG_SESSION,
    FitWriter,
    fit_time,
    semicircles,
)

START = fit_time("2024-06-01T09:00:00Z")
START_UNIX = datetime(2024, 6, 1, 9, tzinfo=timezone.utc).timestamp()
STEP_S = 10

# A loop round the Serpentine, Hyde Park, London
HYDE_PARK = [
    (51.5052, -0.1745),
    (51.5061, -0.1712),
    (51.5073, -0.1669),
    (51.5082, -0.1636),
    (51.5067, -0.1625),
    (51.5047, -0.1660),
    (51.5040, -0.1700),
    (51.5045, -0.1735),
]
SYDNEY_OPERA_HOUSE = (-33.8568, 151.2153)
TORONTO_CITY_HALL = (43.6534, -79.3841)
MID_ATLANTIC = (40.0, -40.0)  # open ocean, under the transatlantic air routes

RECORD_FIELDS = [
    (253, "uint32"),
    (0, "sint32"),
    (1, "sint32"),
    (2, "uint16"),
    (3, "uint8"),
    (4, "uint8"),
    (5, "uint32"),
    (6, "uint16"),
    (7, "uint16"),
    (13, "sint8"),
    (31, "uint8"),
]
SUMMARY_FIELDS = [(253, "uint32"), (2, "uint32"), (7, "uint32"), (8, "uint32"), (9, "uint32")]
EVENT_FIELDS = [(253, "uint32"), (0, "enum"), (1, "enum"), (4, "uint8")]
TIMER, START_EVENT, STOP, STOP_ALL = 0, 0, 1, 4
CYCLING = 2


def record_values(i, lat, lon, t):
    return {
        253: t,
        0: semicircles(lat),
        1: semicircles(lon),
        2: round((35 + 0.4 * i + 500) * 5),  # altitude: scale 5, offset 500
        3: 120 + i,
        4: 80 + i % 5,
        5: 2500 * i,  # distance: scale 100
        6: 5000 + 37 * i,  # speed: scale 1000
        7: 180 + 3 * i,
        13: 18 - i % 3,
        31: 3 + i % 4,
    }


def activity(points=HYDE_PARK, *, big_endian=False, pause_after=None, pause_s=600, header_size=14):
    """file_id, device_info, timer events, records every STEP_S seconds, one lap and a session.
    `pause_after=k` stops the timer after record k-1 and restarts it `pause_s` later."""
    w = FitWriter()
    be = {"big_endian": big_endian}
    w.define(
        0, MESG_FILE_ID, [(0, "enum"), (1, "uint16"), (2, "uint16"), (3, "uint32z"), (4, "uint32")], **be
    )
    w.message(0, {0: 4, 1: 1, 2: 3121, 3: 3_900_000_001, 4: START})
    w.define(
        1,
        MESG_DEVICE_INFO,
        [(253, "uint32"), (0, "uint8"), (2, "uint16"), (4, "uint16"), (5, "uint16"), (27, "string", 12)],
        **be,
    )
    w.message(1, {253: START, 0: 0, 2: 1, 4: 3121, 5: 2650, 27: "Edge 530"})
    w.define(2, MESG_EVENT, EVENT_FIELDS, **be)
    w.message(2, {253: START, 0: TIMER, 1: START_EVENT, 4: 0})
    w.define(3, MESG_RECORD, RECORD_FIELDS, **be)
    t = START
    for i, (lat, lon) in enumerate(points):
        if i == pause_after:
            w.message(2, {253: t - STEP_S + 1, 0: TIMER, 1: STOP, 4: 0})
            t += pause_s
            w.message(2, {253: t, 0: TIMER, 1: START_EVENT, 4: 0})
        w.message(3, record_values(i, lat, lon, t))
        t += STEP_S
    end = t - STEP_S
    elapsed, timer = end - START, end - START - (pause_s if pause_after else 0)
    w.define(4, MESG_LAP, [*SUMMARY_FIELDS, (25, "enum")], **be)
    w.message(4, {253: end, 2: START, 7: elapsed * 1000, 8: timer * 1000, 9: 2500 * (len(points) - 1), 25: 2})
    w.define(5, MESG_SESSION, [*SUMMARY_FIELDS, (5, "enum"), (6, "enum")], **be)
    w.message(
        5, {253: end, 2: START, 7: elapsed * 1000, 8: timer * 1000, 9: 2500 * (len(points) - 1), 5: 2, 6: 0}
    )
    w.message(2, {253: end, 0: TIMER, 1: STOP_ALL, 4: 0})
    return w.to_bytes(header_size=header_size)


def oracle(data):
    """fitdecode's data messages as (name, {field: value}), with CRC and parse errors raised."""
    out = []
    reader = fitdecode.FitReader(
        io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE, error_handling=fitdecode.ErrorHandling.RAISE
    )
    with reader as fit:
        for frame in fit:
            if frame.frame_type == fitdecode.FIT_FRAME_DATA:
                fields = {}
                for f in frame.fields:
                    fields.setdefault(f.name, f.value)  # an expanded component never overrides the field
                out.append((frame.name, fields))
    return out


def messages(data, name):
    return [fields for n, fields in oracle(data) if n == name]


def unix(value):
    return None if value is None else value.timestamp()


def same(got, expected):
    """`got` is placewise's float (NaN when invalid); `expected` fitdecode's value (None when invalid)."""
    if expected is None:
        return got is None or np.isnan(got)
    return got == pytest.approx(expected, rel=1e-12, abs=1e-9)


TRACK_FIELDS = {
    "ele": ("enhanced_altitude", "altitude"),
    "speed": ("enhanced_speed", "speed"),
    "hr": ("heart_rate",),
    "cadence": ("cadence",),
    "power": ("power",),
    "temperature": ("temperature",),
    "accuracy": ("gps_accuracy",),
}


def assert_matches_fitdecode(fit, data):
    """Every record fitdecode reports with a position is a track point with the same values; the
    rest are counted as skipped."""
    records = messages(data, "record")
    located = [r for r in records if r.get("position_lat") is not None and r.get("position_long") is not None]
    assert len(fit.track) == len(located)
    assert fit.skipped_records == len(records) - len(located)
    for i, r in enumerate(located):
        assert fit.track.time[i] == unix(r["timestamp"])
        assert fit.track.lat[i] == pytest.approx(r["position_lat"] * 180 / 2**31, abs=1e-12)
        assert fit.track.lon[i] == pytest.approx(r["position_long"] * 180 / 2**31, abs=1e-12)
        for column, names in TRACK_FIELDS.items():
            expected = next((r[n] for n in names if r.get(n) is not None), None)
            values = getattr(fit.track, column)
            assert same(None if values is None else values[i], expected), (i, column)
        assert same(None if fit.distance is None else fit.distance[i], r.get("distance")), (i, "distance")


def assert_summaries_match(ours, theirs):
    assert len(ours) == len(theirs)
    for a, b in zip(ours, theirs, strict=True):
        assert a.sport == b.get("sport")
        assert a.start_time == unix(b.get("start_time"))
        assert a.end_time == unix(b.get("timestamp"))
        assert same(a.total_elapsed_time, b.get("total_elapsed_time"))
        assert same(a.total_timer_time, b.get("total_timer_time"))
        assert same(a.total_distance, b.get("total_distance"))
