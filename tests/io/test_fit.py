"""FIT activity reader. Fixtures (fit_kit) come from the spec-following encoder in fit_writer.py;
fitdecode, an independent MIT decoder, first confirms each fixture decodes to the intended values,
then placewise must agree with it field by field. Every coordinate is a public place or open ocean."""

import io
from datetime import datetime, timezone

import numpy as np
import pytest
from fit_kit import (
    HYDE_PARK,
    MID_ATLANTIC,
    RECORD_FIELDS,
    START,
    START_UNIX,
    SYDNEY_OPERA_HOUSE,
    TORONTO_CITY_HALL,
    activity,
    assert_matches_fitdecode,
    assert_summaries_match,
    messages,
    oracle,
    record_values,
    unix,
)
from fit_writer import (
    MESG_RECORD,
    FitWriter,
    semicircles,
)

from placewise.io.fit import FitFile, read_fit
from placewise.tracks import Track

# --- the fixture itself, as fitdecode reads it ---


def test_fixture_decodes_in_fitdecode_to_the_intended_values():
    data = activity()
    (file_id,) = messages(data, "file_id")
    assert file_id["type"] == "activity" and file_id["manufacturer"] == "garmin"
    assert file_id["time_created"] == datetime(2024, 6, 1, 9, tzinfo=timezone.utc)
    first = messages(data, "record")[0]
    assert first["position_lat"] * 180 / 2**31 == pytest.approx(51.5052, abs=1e-7)
    assert first["position_long"] * 180 / 2**31 == pytest.approx(-0.1745, abs=1e-7)
    assert first["altitude"] == pytest.approx(35.0)
    assert first["speed"] == pytest.approx(5.0)
    assert first["heart_rate"] == 120 and first["temperature"] == 18
    (session,) = messages(data, "session")
    assert session["sport"] == "cycling" and session["total_elapsed_time"] == pytest.approx(70.0)


# --- placewise against fitdecode ---


def test_track_matches_fitdecode_field_by_field():
    data = activity()
    fit = read_fit(data)
    assert isinstance(fit, FitFile) and isinstance(fit.track, Track)
    assert_matches_fitdecode(fit, data)
    assert fit.track.time[0] == START_UNIX  # the FIT epoch is 1989-12-31T00:00:00Z
    np.testing.assert_allclose(fit.track.lat, [p[0] for p in HYDE_PARK], atol=1e-7)
    np.testing.assert_allclose(fit.track.lon, [p[1] for p in HYDE_PARK], atol=1e-7)
    assert fit.track.ele[0] == pytest.approx(35.0) and fit.track.speed[1] == pytest.approx(5.037)
    assert fit.distance[-1] == pytest.approx(175.0)
    assert fit.track.segments == (0,)
    assert fit.skipped_records == 0


def test_laps_sessions_and_device_match_fitdecode():
    data = activity()
    fit = read_fit(data)
    assert_summaries_match(fit.laps, messages(data, "lap"))
    assert_summaries_match(fit.sessions, messages(data, "session"))
    assert fit.sessions[0].sport == "cycling" and fit.sessions[0].total_distance == pytest.approx(175.0)
    (file_id,) = messages(data, "file_id")
    (info,) = messages(data, "device_info")
    assert fit.file_type == file_id["type"] == "activity"
    assert fit.time_created == unix(file_id["time_created"])
    assert fit.device.manufacturer_name == file_id["manufacturer"] == "garmin"
    assert fit.device.manufacturer == 1 and fit.device.product == 3121
    assert fit.device.serial_number == file_id["serial_number"]
    assert fit.device.product_name == info["product_name"] == "Edge 530"
    assert fit.device.software_version == pytest.approx(info["software_version"]) == pytest.approx(26.5)
    assert [d.device_index for d in fit.devices] == [0] and info["device_index"] == "creator"


def test_meta_and_sources(tmp_path):
    data = activity()
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
    assert_matches_fitdecode(fit, data)
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
        record = record_values(i % 100, lat + i * 1e-6, lon, START + i)
        if i % 2:
            del record[253]
            w.message(1, record, time_offset=(START + i) & 31)
        else:
            w.message(0, record)
    data = w.to_bytes()
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
    np.testing.assert_array_equal(fit.track.time, START_UNIX + np.arange(300))
    assert np.isnan(fit.track.power[150]) and fit.track.power[151] == 180 + 3 * 51


def test_big_endian_definitions_match_fitdecode_and_little_endian():
    data = activity(big_endian=True)
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
    assert_summaries_match(fit.sessions, messages(data, "session"))
    little = read_fit(activity())
    for column in little.track.columns:
        np.testing.assert_array_equal(getattr(fit.track, column), getattr(little.track, column))
    assert fit.device == little.device


def test_southern_and_eastern_hemispheres_big_endian():
    lat, lon = SYDNEY_OPERA_HOUSE
    data = activity([(lat, lon), (lat + 1e-3, lon + 1e-3)], big_endian=True)
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
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
        w.message(1, record_values(i, lat + i * 1e-4, lon, START + i), dev_values=(7 + i, 1.5 * i))
    data = w.to_bytes()
    records = messages(data, "record")
    assert [r["doughnuts"] for r in records] == [7, 8, 9]  # fitdecode does see them
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
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
    assert_matches_fitdecode(fit, data)
    assert fit.track.ele.tolist() == pytest.approx([13_000, 13_001, 13_002])
    assert fit.track.speed[0] == pytest.approx(250.0)
    assert fit.track.hr is None and fit.distance is None  # absent fields are absent columns


def test_invalid_values_skip_records_without_a_position():
    w = FitWriter()
    w.define(0, MESG_RECORD, RECORD_FIELDS)
    lat, lon = HYDE_PARK[0]
    w.message(0, record_values(0, lat, lon, START))
    w.message(0, {253: START + 1, 3: 130})  # every other field written as its invalid value
    no_hr = record_values(2, *HYDE_PARK[1], START + 2)
    no_hr[3] = 0xFF
    w.message(0, no_hr)
    no_lon = record_values(3, *HYDE_PARK[2], START + 3)
    no_lon[1] = 0x7FFFFFFF
    w.message(0, no_lon)
    data = w.to_bytes()
    records = messages(data, "record")
    assert records[1]["position_lat"] is None and records[2]["heart_rate"] is None
    assert records[3]["position_long"] is None
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
    assert len(fit.track) == 2 and fit.skipped_records == 2
    assert fit.track.hr[0] == 120 and np.isnan(fit.track.hr[1])


def test_timer_stop_and_start_split_segments():
    data = activity(pause_after=5)
    events = [(e["event"], e["event_type"]) for e in messages(data, "event")]
    assert events == [("timer", "start"), ("timer", "stop"), ("timer", "start"), ("timer", "stop_all")]
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
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
    first = activity(HYDE_PARK[:3])
    second = activity([TORONTO_CITY_HALL])
    data = first + second
    fit = read_fit(data)
    assert_matches_fitdecode(fit, data)
    assert len(fit.track) == 4 and len(fit.sessions) == 2


def test_twelve_byte_header_and_zero_header_crc():
    for data in (activity(header_size=12), FitWriter().to_bytes(header_crc=False)):
        oracle(data)  # valid for fitdecode too
    assert len(read_fit(activity(header_size=12)).track) == len(HYDE_PARK)
    empty = read_fit(FitWriter().to_bytes())
    assert len(empty.track) == 0 and empty.device is None and empty.file_type is None
