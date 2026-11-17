"""TCX (Garmin Training Center XML v2) reading and writing. Fixtures follow Garmin's example layout
(Activities > Activity > Lap > Track > Trackpoint, TPX extensions); every point is in Central Park, New York.
"""

import warnings

import numpy as np
import pytest

from placewise.io._track_common import TrackReadWarning
from placewise.io.tcx import read_tcx, write_tcx
from placewise.tracks import Track, TrackMeta

T0 = 1717246800.0  # 2024-06-01T13:00:00Z

HEAD = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"
  xmlns:ns3="http://www.garmin.com/xmlschemas/ActivityExtension/v2"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:schemaLocation="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2
    http://www.garmin.com/xmlschemas/TrainingCenterDatabasev2.xsd">
"""


def _point(time, lat=None, lon=None, ele=None, hr=None, cad=None, speed=None, watts=None, run_cad=None):
    parts = [f"<Trackpoint><Time>{time}</Time>"]
    if lat is not None:
        parts.append(
            f"<Position><LatitudeDegrees>{lat}</LatitudeDegrees><LongitudeDegrees>{lon}</LongitudeDegrees>"
            "</Position>"
        )
    if ele is not None:
        parts.append(f"<AltitudeMeters>{ele}</AltitudeMeters>")
    parts.append("<DistanceMeters>0.0</DistanceMeters>")  # present in real files, not a column
    if hr is not None:
        parts.append(f"<HeartRateBpm><Value>{hr}</Value></HeartRateBpm>")
    if cad is not None:
        parts.append(f"<Cadence>{cad}</Cadence>")
    tpx = []
    if speed is not None:
        tpx.append(f"<ns3:Speed>{speed}</ns3:Speed>")
    if run_cad is not None:
        tpx.append(f"<ns3:RunCadence>{run_cad}</ns3:RunCadence>")
    if watts is not None:
        tpx.append(f"<ns3:Watts>{watts}</ns3:Watts>")
    if tpx:
        parts.append(f"<Extensions><ns3:TPX>{''.join(tpx)}</ns3:TPX></Extensions>")
    parts.append("</Trackpoint>")
    return "".join(parts)


def _lap(start, *tracks):
    body = "".join(f"<Track>{''.join(points)}</Track>" for points in tracks)
    return (
        f'<Lap StartTime="{start}"><TotalTimeSeconds>10.0</TotalTimeSeconds>'
        "<DistanceMeters>50.0</DistanceMeters><Calories>3</Calories><Intensity>Active</Intensity>"
        f"<TriggerMethod>Manual</TriggerMethod>{body}</Lap>"
    )


RIDE = (
    HEAD
    + """<Activities><Activity Sport="Biking"><Id>2024-06-01T13:00:00Z</Id>"""
    + _lap(
        "2024-06-01T13:00:00Z",
        [
            _point("2024-06-01T13:00:00Z", 40.7812, -73.9665, 40.2, 118, 80, 5.5, 180),
            _point("2024-06-01T13:00:05Z", 40.7815, -73.9662, 40.6, 121, 82, 5.75, 190),
            _point("2024-06-01T13:00:10.500Z", 40.7818, -73.9659, 41.0, 124, 84, 6.0, 200),
        ],
    )
    + _lap(
        "2024-06-01T13:00:15Z",
        [
            _point("2024-06-01T13:00:15Z", 40.7821, -73.9656, 41.4, 126, 85, 6.25, 210),
            _point("2024-06-01T13:00:20Z", 40.7824, -73.9653, 41.8, 128, 86, 6.5, 220),
        ],
        [  # a second Track inside one Lap: the recording was paused and resumed
            _point("2024-06-01T13:01:00Z", 40.7827, -73.9650, 42.2, 130, 88, 6.75, 230),
        ],
    )
    + """<Creator xsi:type="Device_t"><Name>Edge 530</Name><UnitId>1</UnitId><ProductID>3121</ProductID>
    </Creator></Activity></Activities></TrainingCenterDatabase>"""
)


def test_reads_points_columns_segments_and_sport():
    (track,) = read_tcx(RIDE.encode())
    assert len(track) == 6
    assert track.columns == ("time", "lat", "lon", "ele", "speed", "hr", "cadence", "power")
    assert track.time[0] == T0 and track.time[2] == T0 + 10.5
    assert track.lat[0] == 40.7812 and track.lon[0] == -73.9665
    assert track.ele[1] == 40.6 and track.hr[2] == 124 and track.cadence[3] == 85
    assert track.speed[1] == 5.75 and track.power[5] == 230
    assert track.segments == (0, 3, 5)  # lap 1, lap 2, the resumed Track inside lap 2
    assert track.meta.activity == "Biking" and track.meta.device == "Edge 530"


def test_trackpoints_without_position_are_skipped_and_counted():
    xml = (
        HEAD
        + '<Activities><Activity Sport="Running"><Id>2024-06-01T13:00:00Z</Id>'
        + _lap(
            "2024-06-01T13:00:00Z",
            [
                _point("2024-06-01T13:00:00Z", hr=100),  # heart rate before the GPS fix
                _point("2024-06-01T13:00:01Z", hr=101),
                _point("2024-06-01T13:00:02Z", 40.7812, -73.9665, hr=102),
                _point("2024-06-01T13:00:03Z", 40.7813, -73.9664, hr=103),
            ],
        )
        + "</Activity></Activities></TrainingCenterDatabase>"
    )
    with pytest.warns(TrackReadWarning, match="2 trackpoint") as caught:
        (track,) = read_tcx(xml.encode())
    assert caught[0].message.skipped == 2
    assert len(track) == 2 and list(track.hr) == [102, 103]
    assert track.ele is None and track.power is None  # columns no point carries are left out


def test_run_cadence_extension_and_multiple_activities():
    xml = (
        HEAD
        + '<Activities><Activity Sport="Running"><Id>2024-06-01T13:00:00Z</Id>'
        + _lap("2024-06-01T13:00:00Z", [_point("2024-06-01T13:00:00Z", 40.7812, -73.9665, run_cad=88)])
        + '</Activity><Activity Sport="Other"><Id>2024-06-01T15:00:00Z</Id>'
        + _lap("2024-06-01T15:00:00Z", [_point("2024-06-01T15:00:00Z", 40.7794, -73.9632)])
        + "</Activity></Activities></TrainingCenterDatabase>"
    )
    run, other = read_tcx(xml.encode())
    assert run.meta.activity == "Running" and run.cadence[0] == 88
    assert other.meta.activity == "Other" and other.time[0] == T0 + 7200


def test_courses_and_path_source(tmp_path):
    xml = (
        HEAD
        + "<Courses><Course><Name>Reservoir loop</Name>"
        + _lap("2024-06-01T13:00:00Z", [])
        + "<Track>"
        + _point("2024-06-01T13:00:00Z", 40.7851, -73.9626)
        + _point("2024-06-01T13:00:30Z", 40.7860, -73.9617)
        + "</Track></Course></Courses></TrainingCenterDatabase>"
    )
    path = tmp_path / "loop.tcx"
    path.write_text(xml, encoding="utf-8")
    (course,) = read_tcx(path)
    assert course.meta.name == "Reservoir loop" and len(course) == 2
    assert course.meta.source == "loop.tcx"


def test_not_tcx_is_an_error():
    with pytest.raises(ValueError, match="TCX"):
        read_tcx(b"<gpx></gpx>")
    with pytest.raises(ValueError, match="well-formed"):  # ParseError is not a ValueError
        read_tcx(RIDE[:200].encode())


def test_write_round_trip():
    original = Track(
        time=T0 + np.array([0.0, 5.0, 10.25, 30.0, 35.0]),
        lat=[40.7812, 40.7815, 40.7818, 40.7821, 40.7824],
        lon=[-73.9665, -73.9662, -73.9659, -73.9656, -73.9653],
        segments=(0, 3),
        meta=TrackMeta(name="Park loop", activity="Biking", device="Edge 530"),
        ele=[40.2, 40.6, 41.0, 41.4, 41.8],
        hr=[118, 121, 124, 126, 128],
        cadence=[80, 82, 84, 85, 86],
        speed=[5.5, 5.75, 6.0, 6.25, 6.5],
        power=[180, 190, 200, 210, 220],
    )
    text = write_tcx(original)
    assert text.startswith("<?xml") and "TrainingCenterDatabase" in text
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # a clean file reads without skips
        (back,) = read_tcx(text.encode())
    assert back.columns == original.columns
    for name in original.columns:
        np.testing.assert_allclose(getattr(back, name), getattr(original, name))
    assert back.segments == (0, 3)
    assert back.meta.activity == "Biking"


def test_write_needs_times_and_maps_unknown_sports_to_other(tmp_path):
    no_times = Track(time=[np.nan, np.nan], lat=[40.78, 40.79], lon=[-73.96, -73.97])
    with pytest.raises(ValueError, match="time"):
        write_tcx(no_times)
    walk = Track(
        time=[T0, T0 + 1], lat=[40.78, 40.79], lon=[-73.96, -73.97], meta=TrackMeta(activity="walking")
    )
    path = tmp_path / "walk.tcx"
    write_tcx(walk, path)
    (back,) = read_tcx(path)
    assert back.meta.activity == "Other"  # the schema allows only Running, Biking and Other
