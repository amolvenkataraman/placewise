"""CSV tracks: header auto-detection, explicit column mappings, the usual time encodings and the writer.
Points are around Nathan Phillips Square, Union Station and the CN Tower in Toronto."""

import io

import numpy as np
import pytest

from placewise.io._track_common import TrackReadWarning
from placewise.io.csv_tracks import read_csv_track, write_csv_track
from placewise.tracks import Track

T0 = 1717243200.0  # 2024-06-01T12:00:00Z


def test_auto_detected_headers_with_units_and_iso_times():
    text = (
        "Timestamp,Latitude,Longitude,Altitude (m),Speed,Heart Rate,Notes\n"
        "2024-06-01T12:00:00Z,43.6525,-79.3835,91.0,1.4,96,start\n"
        "2024-06-01T08:00:05-04:00,43.6453,-79.3806,80.5,1.5,99,\n"  # Toronto local time, EDT
        "2024-06-01T12:00:10.5Z,43.6426,-79.3871,76.0,,101,tower\n"
    )
    track = read_csv_track(text.encode())
    assert track.columns == ("time", "lat", "lon", "ele", "speed", "hr")
    assert list(track.time) == [T0, T0 + 5, T0 + 10.5]
    assert track.lat[2] == 43.6426 and track.lon[2] == -79.3871
    assert track.ele[1] == 80.5 and list(track.hr) == [96, 99, 101]
    assert np.isnan(track.speed[2])  # an empty cell
    assert track.segments == (0,)


@pytest.mark.parametrize(
    ("header", "sep"),
    [
        ("date_time,lat,lng,alt,hr,cadence", ","),
        ("time;latitude;long;elevation;heart_rate;cad", ";"),
        ("TIME\tLAT\tLON\tELE\tBPM\tCADENCE", "\t"),
    ],
)
def test_header_aliases_and_delimiters(header, sep):
    rows = [
        [f"{T0:.0f}", "43.6525", "-79.3835", "91", "96", "70"],
        [f"{T0 + 1:.0f}", "43.6453", "-79.3806", "80", "99", "72"],
    ]
    text = "\n".join([header, *(sep.join(r) for r in rows)])
    track = read_csv_track(text.encode())
    assert list(track.time) == [T0, T0 + 1]  # unix seconds
    assert list(track.ele) == [91, 80] and list(track.hr) == [96, 99] and list(track.cadence) == [70, 72]


def test_unix_milliseconds_and_decimal_commas():
    text = f"timestamp;lat;lon\n{T0 * 1000:.0f};43,6525;-79,3835\n{(T0 + 2.5) * 1000:.0f};43,6453;-79,3806\n"
    track = read_csv_track(text.encode())
    assert list(track.time) == [T0, T0 + 2.5]
    assert track.lat[0] == 43.6525 and track.lon[1] == -79.3806


def test_strptime_format_naive_is_utc_and_offsets_are_honoured():
    text = "time,lat,lon\n01/06/2024 12:00:00,43.6525,-79.3835\n01/06/2024 12:00:30,43.6453,-79.3806\n"
    track = read_csv_track(text.encode(), time_format="%d/%m/%Y %H:%M:%S")
    assert list(track.time) == [T0, T0 + 30]
    text = "time,lat,lon\n01/06/2024 08:00:00 -0400,43.6525,-79.3835\n"
    track = read_csv_track(text.encode(), time_format="%d/%m/%Y %H:%M:%S %z")
    assert track.time[0] == T0


def test_explicit_column_mapping():
    text = "GPS Time,Y,X,Height,Pulse\n2024-06-01 12:00:00,43.6525,-79.3835,91,96\n"
    track = read_csv_track(
        text.encode(), columns={"time": "GPS Time", "lat": "Y", "lon": "X", "ele": "Height", "hr": "Pulse"}
    )
    assert track.time[0] == T0 and track.lat[0] == 43.6525 and track.ele[0] == 91 and track.hr[0] == 96
    with pytest.raises(ValueError, match="Nope"):
        read_csv_track(text.encode(), columns={"lat": "Nope", "lon": "X"})
    with pytest.raises(ValueError, match="track column"):
        read_csv_track(text.encode(), columns={"latitude": "Y", "lon": "X"})


def test_no_time_column_and_rows_without_position():
    # a row of empty cells is blank and passes silently; half a position or a non-number is counted
    text = "lat,lon\n43.6525,-79.3835\n,\n43.6500,\nnot a number,-79.3806\n43.6426,-79.3871\n"
    with pytest.warns(TrackReadWarning, match="2 row") as caught:
        track = read_csv_track(io.BytesIO(text.encode()))
    assert caught[0].message.skipped == 2
    assert len(track) == 2 and np.all(np.isnan(track.time))


def test_missing_position_columns_is_an_error():
    with pytest.raises(ValueError, match="latitude"):
        read_csv_track(b"time,x,y\n1,2,3\n")


def test_write_round_trip(tmp_path):
    original = Track(
        time=T0 + np.array([0.0, 5.0, 10.25, 60.0]),
        lat=[43.6525, 43.6453, 43.6426, 43.6430],
        lon=[-79.3835, -79.3806, -79.3871, -79.3880],
        segments=(0, 3),
        ele=[91.0, 80.5, np.nan, 77.0],
        hr=[96, 99, 101, 102],
    )
    path = tmp_path / "walk.csv"
    write_csv_track(original, path)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert header == "time,lat,lon,ele,hr,segment"
    back = read_csv_track(path)
    assert back.columns == original.columns and back.segments == (0, 3)
    for name in original.columns:
        np.testing.assert_array_equal(getattr(back, name), getattr(original, name))
    assert back.meta.source == "walk.csv"
