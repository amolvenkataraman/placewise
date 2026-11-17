"""FIT activity reader. Fixtures come from the spec-following encoder in fit_writer.py; fitdecode, an
independent MIT decoder, first confirms each fixture decodes to the intended values, then placewise
must agree with it field by field. Every coordinate is a public place or open ocean."""

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
    crc16,
    fit_time,
    semicircles,
)

from placewise.constants import fit as fit_constants
from placewise.io.fit import FitError, FitFile, _crc16, read_fit
from placewise.tracks import Track

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


def _record(i, lat, lon, t):
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


def _activity(points=HYDE_PARK, *, big_endian=False, pause_after=None, pause_s=600, header_size=14):
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
        w.message(3, _record(i, lat, lon, t))
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


def _oracle(data):
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


def _messages(data, name):
    return [fields for n, fields in _oracle(data) if n == name]


def _unix(value):
    return None if value is None else value.timestamp()


def _same(got, expected):
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


def _assert_matches_fitdecode(fit, data):
    """Every record fitdecode reports with a position is a track point with the same values; the
    rest are counted as skipped."""
    records = _messages(data, "record")
    located = [r for r in records if r.get("position_lat") is not None and r.get("position_long") is not None]
    assert len(fit.track) == len(located)
    assert fit.skipped_records == len(records) - len(located)
    for i, r in enumerate(located):
        assert fit.track.time[i] == _unix(r["timestamp"])
        assert fit.track.lat[i] == pytest.approx(r["position_lat"] * 180 / 2**31, abs=1e-12)
        assert fit.track.lon[i] == pytest.approx(r["position_long"] * 180 / 2**31, abs=1e-12)
        for column, names in TRACK_FIELDS.items():
            expected = next((r[n] for n in names if r.get(n) is not None), None)
            values = getattr(fit.track, column)
            assert _same(None if values is None else values[i], expected), (i, column)
        assert _same(None if fit.distance is None else fit.distance[i], r.get("distance")), (i, "distance")


def _assert_summaries_match(ours, theirs):
    assert len(ours) == len(theirs)
    for a, b in zip(ours, theirs, strict=True):
        assert a.sport == b.get("sport")
        assert a.start_time == _unix(b.get("start_time"))
        assert a.end_time == _unix(b.get("timestamp"))
        assert _same(a.total_elapsed_time, b.get("total_elapsed_time"))
        assert _same(a.total_timer_time, b.get("total_timer_time"))
        assert _same(a.total_distance, b.get("total_distance"))


# --- the fixture itself, as fitdecode reads it ---


def test_fixture_decodes_in_fitdecode_to_the_intended_values():
    data = _activity()
    (file_id,) = _messages(data, "file_id")
    assert file_id["type"] == "activity" and file_id["manufacturer"] == "garmin"
    assert file_id["time_created"] == datetime(2024, 6, 1, 9, tzinfo=timezone.utc)
    first = _messages(data, "record")[0]
    assert first["position_lat"] * 180 / 2**31 == pytest.approx(51.5052, abs=1e-7)
    assert first["position_long"] * 180 / 2**31 == pytest.approx(-0.1745, abs=1e-7)
    assert first["altitude"] == pytest.approx(35.0)
    assert first["speed"] == pytest.approx(5.0)
    assert first["heart_rate"] == 120 and first["temperature"] == 18
    (session,) = _messages(data, "session")
    assert session["sport"] == "cycling" and session["total_elapsed_time"] == pytest.approx(70.0)


# --- placewise against fitdecode ---


def test_track_matches_fitdecode_field_by_field():
    data = _activity()
    fit = read_fit(data)
    assert isinstance(fit, FitFile) and isinstance(fit.track, Track)
    _assert_matches_fitdecode(fit, data)
    assert fit.track.time[0] == START_UNIX  # the FIT epoch is 1989-12-31T00:00:00Z
    np.testing.assert_allclose(fit.track.lat, [p[0] for p in HYDE_PARK], atol=1e-7)
    np.testing.assert_allclose(fit.track.lon, [p[1] for p in HYDE_PARK], atol=1e-7)
    assert fit.track.ele[0] == pytest.approx(35.0) and fit.track.speed[1] == pytest.approx(5.037)
    assert fit.distance[-1] == pytest.approx(175.0)
    assert fit.track.segments == (0,)
    assert fit.skipped_records == 0


def test_laps_sessions_and_device_match_fitdecode():
    data = _activity()
    fit = read_fit(data)
    _assert_summaries_match(fit.laps, _messages(data, "lap"))
    _assert_summaries_match(fit.sessions, _messages(data, "session"))
    assert fit.sessions[0].sport == "cycling" and fit.sessions[0].total_distance == pytest.approx(175.0)
    (file_id,) = _messages(data, "file_id")
    (info,) = _messages(data, "device_info")
    assert fit.file_type == file_id["type"] == "activity"
    assert fit.time_created == _unix(file_id["time_created"])
    assert fit.device.manufacturer_name == file_id["manufacturer"] == "garmin"
    assert fit.device.manufacturer == 1 and fit.device.product == 3121
    assert fit.device.serial_number == file_id["serial_number"]
    assert fit.device.product_name == info["product_name"] == "Edge 530"
    assert fit.device.software_version == pytest.approx(info["software_version"]) == pytest.approx(26.5)
    assert [d.device_index for d in fit.devices] == [0] and info["device_index"] == "creator"


def test_meta_and_sources(tmp_path):
    data = _activity()
    path = tmp_path / "serpentine.fit"
    path.write_bytes(data)
    from_path = read_fit(path)
    assert from_path.track.meta.activity == "cycling"
    assert from_path.track.meta.device == "Edge 530"
    assert from_path.track.meta.source == "serpentine.fit"
    for source in (str(path), data, bytearray(data), memoryview(data), io.BytesIO(data)):
        np.testing.assert_array_equal(read_fit(source).track.lat, from_path.track.lat)
    assert read_fit(data).track.meta.source is None


def test_compressed_timestamps_match_fitdecode():
    # 28 s past a 32 s boundary, so the offsets below wrap into the next block
    t0 = START + 28 - START % 32
    w = FitWriter()
    w.define(0, MESG_RECORD, [(253, "uint32"), (0, "sint32"), (1, "sint32"), (3, "uint8")])
    lat, lon = TORONTO_CITY_HALL
    w.message(0, {253: t0, 0: semicircles(lat), 1: semicircles(lon), 3: 100})
    w.define(1, MESG_RECORD, [(0, "sint32"), (1, "sint32"), (3, "uint8")])
    offsets = [30, 31, 2, 7, 7, 20, 3]  # 2 and 3 roll over into the next 32 s block
    for k, offset in enumerate(offsets, 1):
        w.message(1, {0: semicircles(lat + k * 1e-4), 1: semicircles(lon), 3: 100 + k}, time_offset=offset)
    data = w.to_bytes()
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    base = t0 - t0 % 32
    expected = [t0, base + 30, base + 31, base + 34, base + 39, base + 39, base + 52, base + 67]
    np.testing.assert_array_equal(fit.track.time - START_UNIX, np.array(expected) - START)


def test_interleaved_and_redefined_definitions_keep_file_order():
    # devices alternate local messages (here a full and a compressed-timestamp record layout) and
    # redefine a local number mid-file; the points must come out in file order regardless
    w = FitWriter()
    w.define(0, MESG_RECORD, RECORD_FIELDS)
    w.define(1, MESG_RECORD, RECORD_FIELDS[1:])
    for i in range(300):
        if i == 150:
            w.define(
                0, MESG_RECORD, [(253, "uint32"), (0, "sint32"), (1, "sint32"), (3, "uint8")], big_endian=True
            )
        lat, lon = HYDE_PARK[i % len(HYDE_PARK)]
        record = _record(i % 100, lat + i * 1e-6, lon, START + i)
        if i % 2:
            del record[253]
            w.message(1, record, time_offset=(START + i) & 31)
        else:
            w.message(0, record)
    data = w.to_bytes()
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    np.testing.assert_array_equal(fit.track.time, START_UNIX + np.arange(300))
    assert np.isnan(fit.track.power[150]) and fit.track.power[151] == 180 + 3 * 51


def test_big_endian_definitions_match_fitdecode_and_little_endian():
    data = _activity(big_endian=True)
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    _assert_summaries_match(fit.sessions, _messages(data, "session"))
    little = read_fit(_activity())
    for column in little.track.columns:
        np.testing.assert_array_equal(getattr(fit.track, column), getattr(little.track, column))
    assert fit.device == little.device


def test_southern_and_eastern_hemispheres_big_endian():
    lat, lon = SYDNEY_OPERA_HOUSE
    data = _activity([(lat, lon), (lat + 1e-3, lon + 1e-3)], big_endian=True)
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert fit.track.lat[0] == pytest.approx(lat, abs=1e-7) and fit.track.lon[0] == pytest.approx(
        lon, abs=1e-7
    )


def test_developer_fields_are_skipped():
    lat, lon = HYDE_PARK[0]
    w = FitWriter()
    w.describe_developer_field(0, 0, 0, "uint16", "doughnuts", "count")
    w.describe_developer_field(0, 1, 5, "float32", "air_power", "W")
    w.define(1, MESG_RECORD, RECORD_FIELDS, dev_fields=[(0, "uint16", 0), (5, "float32", 1)])
    for i in range(3):
        w.message(1, _record(i, lat + i * 1e-4, lon, START + i), dev_values=(7 + i, 1.5 * i))
    data = w.to_bytes()
    records = _messages(data, "record")
    assert [r["doughnuts"] for r in records] == [7, 8, 9]  # fitdecode does see them
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert len(fit.track) == 3 and fit.track.hr.tolist() == [120, 121, 122]


def test_enhanced_altitude_and_speed():
    # a cruising airliner over the mid-Atlantic, above the 12 607 m (65 535 / 5 - 500) that the
    # uint16 altitude field can hold
    lat, lon = MID_ATLANTIC
    w = FitWriter()
    w.define(0, MESG_RECORD, [(253, "uint32"), (0, "sint32"), (1, "sint32"), (73, "uint32"), (78, "uint32")])
    for i in range(3):
        w.message(
            0,
            {
                253: START + i,
                0: semicircles(lat),
                1: semicircles(lon + i * 0.003),
                73: 250_000 + i,
                78: (13_000 + i + 500) * 5,
            },
        )
    data = w.to_bytes()
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert fit.track.ele.tolist() == pytest.approx([13_000, 13_001, 13_002])
    assert fit.track.speed[0] == pytest.approx(250.0)
    assert fit.track.hr is None and fit.distance is None  # absent fields are absent columns


def test_invalid_values_skip_records_without_a_position():
    w = FitWriter()
    w.define(0, MESG_RECORD, RECORD_FIELDS)
    lat, lon = HYDE_PARK[0]
    w.message(0, _record(0, lat, lon, START))
    w.message(0, {253: START + 1, 3: 130})  # every other field written as its invalid value
    no_hr = _record(2, *HYDE_PARK[1], START + 2)
    no_hr[3] = 0xFF
    w.message(0, no_hr)
    no_lon = _record(3, *HYDE_PARK[2], START + 3)
    no_lon[1] = 0x7FFFFFFF
    w.message(0, no_lon)
    data = w.to_bytes()
    records = _messages(data, "record")
    assert records[1]["position_lat"] is None and records[2]["heart_rate"] is None
    assert records[3]["position_long"] is None
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert len(fit.track) == 2 and fit.skipped_records == 2
    assert fit.track.hr[0] == 120 and np.isnan(fit.track.hr[1])


def test_timer_stop_and_start_split_segments():
    data = _activity(pause_after=5)
    events = [(e["event"], e["event_type"]) for e in _messages(data, "event")]
    assert events == [("timer", "start"), ("timer", "stop"), ("timer", "start"), ("timer", "stop_all")]
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert fit.track.segments == (0, 5)
    assert [len(s) for s in fit.track.iter_segments()] == [5, 3]
    assert fit.sessions[0].total_timer_time == pytest.approx(70.0)
    assert fit.sessions[0].total_elapsed_time == pytest.approx(670.0)


def test_no_positions_gives_an_empty_track():
    w = FitWriter()
    w.define(0, MESG_RECORD, [(253, "uint32"), (3, "uint8")])  # an indoor ride: heart rate, no GPS
    for i in range(4):
        w.message(0, {253: START + i, 3: 110 + i})
    fit = read_fit(w.to_bytes())
    assert len(fit.track) == 0 and fit.skipped_records == 4
    assert fit.laps == () and fit.sessions == () and fit.device is None


def test_chained_files_are_read_in_order():
    first = _activity(HYDE_PARK[:3])
    second = _activity([TORONTO_CITY_HALL])
    data = first + second
    fit = read_fit(data)
    _assert_matches_fitdecode(fit, data)
    assert len(fit.track) == 4 and len(fit.sessions) == 2


def test_twelve_byte_header_and_zero_header_crc():
    for data in (_activity(header_size=12), FitWriter().to_bytes(header_crc=False)):
        _oracle(data)  # valid for fitdecode too
    assert len(read_fit(_activity(header_size=12)).track) == len(HYDE_PARK)
    empty = read_fit(FitWriter().to_bytes())
    assert len(empty.track) == 0 and empty.device is None and empty.file_type is None


# --- corrupt and malformed files ---


def test_corrupt_crc_fails_clearly():
    data = bytearray(_activity())
    data[60] ^= 0x01  # one bit, inside the data records
    with pytest.raises(fitdecode.FitCRCError):
        _oracle(bytes(data))  # fitdecode agrees the file is corrupt
    with pytest.raises(FitError, match="CRC"):
        read_fit(bytes(data))
    assert issubclass(FitError, ValueError)
    stored = bytearray(_activity())
    stored[-1] ^= 0xFF  # the stored file CRC itself
    with pytest.raises(FitError, match="CRC"):
        read_fit(bytes(stored))


def test_corrupt_header_crc_fails_clearly():
    data = bytearray(_activity())
    data[12] ^= 0x01
    with pytest.raises(FitError, match="header CRC"):
        read_fit(bytes(data))


def test_check_crc_can_be_turned_off():
    data = bytearray(_activity())
    data[-1] ^= 0xFF
    assert len(read_fit(bytes(data), check_crc=False).track) == len(HYDE_PARK)


def test_malformed_files():
    data = _activity()
    with pytest.raises(FitError, match="FIT"):
        read_fit(b"not a fit file at all")
    with pytest.raises(FitError, match=r"\.FIT"):
        read_fit(data[:8] + b"XFIT" + data[12:])
    with pytest.raises(FitError, match="truncated"):
        read_fit(data[:-10])
    w = FitWriter()
    w.define(0, MESG_RECORD, [(253, "uint32")])
    w.message(0, {253: START})
    body = bytearray(w.to_bytes())
    body[14 + 9] = 0x05  # the data message now names local message 5, never defined
    body[-2:] = crc16(bytes(body[:-2])).to_bytes(2, "little")
    with pytest.raises(FitError, match="local message 5"):
        read_fit(bytes(body))


# --- internals checked against independent references ---


@pytest.mark.parametrize("n", [0, 1, 2, 15, 16, 17, 255, 1000, 4097, 100_003])
def test_crc_matches_the_sdk_nibble_algorithm(n):
    data = np.random.default_rng(n).integers(0, 256, n, dtype=np.uint8).tobytes()
    assert _crc16(data) == crc16(data)


def test_profile_constants_agree_with_fitdecode():
    from fitdecode import profile

    for mesg_num, fields in fit_constants.MESSAGE_FIELDS.items():
        theirs = profile.MESSAGE_TYPES[mesg_num]
        for num, field in fields.items():
            reference = theirs.fields[num]
            assert field.name == reference.name, (mesg_num, num)
            assert field.scale == (reference.scale or 1), field.name
            assert field.offset == (reference.offset or 0), field.name
    for number, name in fit_constants.SPORTS.items():
        assert profile.FIELD_TYPES["sport"].enum[number] == name
    for number, name in fit_constants.MANUFACTURERS.items():
        assert profile.FIELD_TYPES["manufacturer"].enum[number] == name
    for number, name in fit_constants.FILE_TYPES.items():
        assert profile.FIELD_TYPES["file"].enum[number] == name
    assert fit_constants.EPOCH_UNIX_S == datetime(1989, 12, 31, tzinfo=timezone.utc).timestamp()
