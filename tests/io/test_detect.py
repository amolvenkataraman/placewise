"""Format detection from content and dispatch to the readers. GPX and FIT are checked by detection
(and by wiring, with stand-in readers), never by parsing: their readers are tested on their own.
Points are at the Sydney Opera House, Central Park and Golden Gate Park."""

import io
import json
import struct
import sys
import types
import zipfile
from functools import reduce

import numpy as np
import pytest

from placewise.io.detect import detect_format, read_track
from placewise.tracks import Track

T0 = 1717246800.0  # 2024-06-01T13:00:00Z

TCX = b"""<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Running"><Id>2024-06-01T13:00:00Z</Id><Lap StartTime="2024-06-01T13:00:00Z">
<Track><Trackpoint><Time>2024-06-01T13:00:00Z</Time><Position><LatitudeDegrees>40.7812</LatitudeDegrees>
<LongitudeDegrees>-73.9665</LongitudeDegrees></Position></Trackpoint></Track></Lap></Activity></Activities>
</TrainingCenterDatabase>"""

KML = b"""<?xml version="1.0" encoding="UTF-8"?>
<!-- exported by a mapping tool -->
<kml xmlns="http://www.opengis.net/kml/2.2"><Placemark><name>Park</name>
<LineString><coordinates>-122.4862,37.7694 -122.4850,37.7697</coordinates></LineString></Placemark></kml>"""

GPX = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE gpx>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1"></gpx>"""

GEOJSON = json.dumps(
    {
        "type": "Feature",
        "properties": {"coordTimes": ["2024-06-01T13:00:00Z", "2024-06-01T13:00:01Z"]},
        "geometry": {"type": "LineString", "coordinates": [[151.2153, -33.8568], [151.2155, -33.8566]]},
    }
).encode()


def _s(body):
    return f"${body}*{reduce(lambda a, c: a ^ ord(c), body, 0):02X}"


NMEA = "\n".join(
    [
        _s("GPGGA,130000.00,3351.408,S,15112.918,E,1,08,0.9,4.5,M,22.1,M,,"),
        _s("GPRMC,130000.00,A,3351.408,S,15112.918,E,10.0,045.0,010624,,,A"),
    ]
).encode()

CSV = b"time,lat,lon\n2024-06-01T13:00:00Z,43.6525,-79.3835\n2024-06-01T13:00:01Z,43.6526,-79.3834\n"


def _kmz():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", KML)
    return buffer.getvalue()


def _fit_header():
    # 14-byte header: size, protocol, profile, data size, ".FIT", header CRC; no records follow
    return struct.pack("<BBHI4sH", 14, 0x20, 2132, 0, b".FIT", 0)


@pytest.mark.parametrize(
    ("data", "name"),
    [
        (_fit_header(), "fit"),
        (_kmz(), "kmz"),
        (GPX, "gpx"),
        (TCX, "tcx"),
        (KML, "kml"),
        (b"\xef\xbb\xbf  " + KML, "kml"),  # a byte order mark and whitespace before the prolog
        (GEOJSON, "geojson"),
        (NMEA, "nmea"),
        (b"2024-06-01 13:00:00.000 " + NMEA, "nmea"),  # a logger's own timestamp in front
        (CSV, "csv"),
    ],
)
def test_detect_format(data, name):
    assert detect_format(data) == name


def test_unknown_xml_and_empty_input_are_errors():
    with pytest.raises(ValueError, match="svg"):
        detect_format(b'<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    with pytest.raises(ValueError, match="empty"):
        detect_format(b"  \n")


@pytest.mark.parametrize(
    ("data", "name", "n_points"),
    [
        (TCX, "tcx", 1),
        (KML, "kml", 2),
        (b"\xef\xbb\xbf\n\n" + KML, "kml", 2),
        (_kmz(), "kmz", 2),
        (GEOJSON, "geojson", 2),
        (NMEA, "nmea", 1),
        (CSV, "csv", 2),
    ],
)
def test_read_track_dispatches_to_the_readers(data, name, n_points):
    tracks, detected = read_track(data)
    assert detected == name
    assert len(tracks) == 1 and isinstance(tracks[0], Track) and len(tracks[0]) == n_points


def test_read_track_from_a_path_keeps_the_file_name(tmp_path):
    path = tmp_path / "ride.dat"  # the extension is ignored: content decides
    path.write_bytes(TCX)
    (track,), detected = read_track(path)
    assert detected == "tcx" and track.meta.source == "ride.dat"
    assert track.time[0] == T0


def test_gpx_and_fit_are_dispatched_lazily(monkeypatch):
    track = Track(time=[T0], lat=[40.7812], lon=[-73.9665])
    seen = {}

    def fake_gpx(source):
        seen["gpx"] = source
        return types.SimpleNamespace(tracks=(track,), routes=(track,), waypoints=())

    def fake_fit(source):
        seen["fit"] = source
        return types.SimpleNamespace(track=track)

    monkeypatch.setitem(sys.modules, "placewise.io.gpx", types.SimpleNamespace(read_gpx=fake_gpx))
    monkeypatch.setitem(sys.modules, "placewise.io.fit", types.SimpleNamespace(read_fit=fake_fit))
    tracks, detected = read_track(GPX)
    assert detected == "gpx" and len(tracks) == 2 and seen["gpx"] == GPX  # tracks, then routes
    tracks, detected = read_track(_fit_header())
    assert detected == "fit" and tracks == [track]
    np.testing.assert_array_equal(tracks[0].lat, [40.7812])
