"""NMEA 0183 logs: GGA, RMC and GLL from any of the common talkers, checksums, date handling and the
midnight rollover. Points are at the Sydney Opera House (S/E hemispheres) and in the open North
Atlantic (N/W)."""

import datetime as dt
import warnings
from functools import reduce

import numpy as np
import pytest

from placewise.io._track_common import TrackReadWarning
from placewise.io.nmea import read_nmea

KNOT = 1852 / 3600


def _s(body):
    """A sentence with its checksum: XOR of every character between $ and *."""
    return f"${body}*{reduce(lambda a, c: a ^ ord(c), body, 0):02X}"


def _unix(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc).timestamp()


# Sydney Opera House: -33.8568, 151.2153 -> 3351.408 S, 15112.918 E
OPERA = [
    _s("GPGGA,093000.00,3351.408,S,15112.918,E,1,08,0.9,4.5,M,22.1,M,,"),
    _s("GPRMC,093000.00,A,3351.408,S,15112.918,E,10.0,045.0,010624,,,A"),
    _s("GPGSV,3,1,11,03,03,111,00,04,15,270,00,06,01,010,00,13,06,292,00"),  # not a fix: ignored
    _s("GNGGA,093001.00,3351.400,S,15112.930,E,2,12,1.2,5.0,M,22.1,M,,"),
    _s("GNRMC,093001.00,A,3351.400,S,15112.930,E,12.5,050.5,010624,,,D"),
    _s("GPVTG,050.5,T,,M,12.5,N,23.2,K,D"),
]


def test_gga_and_rmc_merge_into_one_fix_per_second():
    track = read_nmea("\r\n".join(OPERA).encode())
    assert len(track) == 2
    assert track.time[0] == _unix(2024, 6, 1, 9, 30) and track.time[1] == track.time[0] + 1
    assert track.lat[0] == pytest.approx(-33.8568) and track.lon[0] == pytest.approx(151.2153)
    assert list(track.satellites) == [8, 12]
    assert list(track.ele) == [4.5, 5.0]
    assert track.speed[0] == pytest.approx(10 * KNOT) and track.speed[1] == pytest.approx(12.5 * KNOT)
    assert list(track.heading) == [45.0, 50.5]
    assert track.accuracy[1] > track.accuracy[0] > 0  # HDOP x UERE: larger HDOP, larger error
    assert track.meta.source == "nmea"


def test_hdop_scaling_is_configurable():
    track = read_nmea("\n".join(OPERA).encode(), uere_m=2.0)
    assert list(track.accuracy) == pytest.approx([1.8, 2.4])
    assert read_nmea("\n".join(OPERA).encode(), uere_m=None).accuracy is None


def test_bad_checksums_are_skipped_and_counted():
    # one changed digit (two identical changes would cancel out in the XOR)
    corrupted = OPERA[3].replace("3351.400", "3351.401")
    truncated = OPERA[4][:40]  # a line cut off mid-write has no checksum at all
    lines = [OPERA[0], OPERA[1], corrupted, truncated, OPERA[2]]
    with pytest.warns(TrackReadWarning, match="checksum") as caught:
        track = read_nmea("\n".join(lines).encode())
    assert caught[0].message.skipped == 2
    assert len(track) == 1


def test_lowercase_hex_checksum_is_accepted():
    body = "GPGGA,093000.00,3351.408,S,15112.918,E,1,08,0.9,4.5,M,22.1,M,,"
    sentence = _s(body)
    lower = sentence[:-2] + sentence[-2:].lower()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # no RMC, so no date: the NaN-time warning is not under test
        assert len(read_nmea(lower.encode())) == 1


def test_date_from_rmc_reaches_earlier_gga_fixes():
    lines = [
        _s("GPGGA,235958.00,3000.000,N,04000.000,W,1,07,1.0,0.0,M,,M,,"),
        _s("GPGGA,235959.00,3000.010,N,04000.010,W,1,07,1.0,0.0,M,,M,,"),
        _s("GPRMC,235959.00,A,3000.010,N,04000.010,W,5.0,010.0,311224,,,A"),  # 31 Dec 2024
    ]
    track = read_nmea("\n".join(lines).encode())
    assert list(track.time) == [_unix(2024, 12, 31, 23, 59, 58), _unix(2024, 12, 31, 23, 59, 59)]
    assert track.lat[0] == pytest.approx(30.0) and track.lon[0] == pytest.approx(-40.0)  # N/W signs


def test_midnight_rollover_without_a_new_rmc():
    lines = [
        _s("GPRMC,235959.00,A,3000.000,N,04000.000,W,5.0,010.0,311224,,,A"),
        _s("GPGGA,235959.00,3000.000,N,04000.000,W,1,07,1.0,0.0,M,,M,,"),
        _s("GPGGA,000000.00,3000.010,N,04000.010,W,1,07,1.0,0.0,M,,M,,"),  # the date has turned
        _s("GPGGA,000001.00,3000.020,N,04000.020,W,1,07,1.0,0.0,M,,M,,"),
    ]
    track = read_nmea("\n".join(lines).encode())
    assert list(np.diff(track.time)) == [1.0, 1.0]
    assert track.time[1] == _unix(2025, 1, 1, 0, 0, 0)


def test_rollover_before_the_first_rmc_counts_backwards():
    lines = [
        _s("GPGGA,235959.00,3000.000,N,04000.000,W,1,07,1.0,0.0,M,,M,,"),
        _s("GPGGA,000000.00,3000.010,N,04000.010,W,1,07,1.0,0.0,M,,M,,"),
        _s("GPRMC,000000.00,A,3000.010,N,04000.010,W,5.0,010.0,010125,,,A"),  # 1 Jan 2025
    ]
    track = read_nmea("\n".join(lines).encode())
    assert track.time[0] == _unix(2024, 12, 31, 23, 59, 59) and track.time[1] == _unix(2025, 1, 1)


def test_gll_and_other_talkers_with_an_explicit_date():
    lines = [
        _s("GLGLL,3351.408,S,15112.918,E,093000.00,A,A"),
        _s("GAGLL,3351.400,S,15112.930,E,093001.00,A,A"),
        _s("BDGLL,3351.392,S,15112.942,E,093002.00,A,A"),
        _s("PGRME,15.0,M,45.0,M,25.0,M"),  # proprietary: ignored
    ]
    track = read_nmea("\n".join(lines).encode(), date=dt.date(2024, 6, 1))
    assert len(track) == 3
    assert track.time[2] == _unix(2024, 6, 1, 9, 30, 2)
    assert track.ele is None and track.satellites is None


def test_no_date_anywhere_gives_nan_times_with_a_warning():
    lines = [_s("GPGLL,3351.408,S,15112.918,E,093000.00,A,A")]
    with pytest.warns(TrackReadWarning, match="date"):
        track = read_nmea("\n".join(lines).encode())
    assert len(track) == 1 and np.isnan(track.time[0])


def test_fixes_without_a_position_are_skipped():
    lines = [
        _s("GPGGA,093000.00,,,,,0,00,99.9,,M,,M,,"),  # no fix yet
        _s("GPRMC,093000.00,V,,,,,,,010624,,,N"),  # the receiver clock knows the date already
        _s("GPGGA,093001.00,3351.408,S,15112.918,E,0,03,9.9,4.5,M,,M,,"),  # a stale position, quality 0
        _s("GPRMC,093001.00,V,3351.408,S,15112.918,E,0.0,,010624,,,N"),
        _s("GPGGA,093002.00,3351.408,S,15112.918,E,1,05,2.0,4.5,M,,M,,"),
    ]
    with pytest.warns(TrackReadWarning, match="no fix"):
        track = read_nmea("\n".join(lines).encode())
    assert len(track) == 1 and track.time[0] == _unix(2024, 6, 1, 9, 30, 2)


def test_logger_prefixes_bom_and_path(tmp_path):
    text = "﻿" + "\n".join(f"2024-06-01 09:30:0{i // 2} {line}" for i, line in enumerate(OPERA[:2]))
    path = tmp_path / "log.nmea"
    path.write_text(text + "\n\n", encoding="utf-8")
    track = read_nmea(path)
    assert len(track) == 1 and track.meta.source == "log.nmea"
    assert track.time[0] == _unix(2024, 6, 1, 9, 30)
