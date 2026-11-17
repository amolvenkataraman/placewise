"""GPX reading and writing. Every coordinate is a public landmark or open ocean."""

import datetime as dt
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from placewise.io.gpx import GpxFile, Waypoint, read_gpx, write_gpx
from placewise.tracks import OPTIONAL_COLUMNS, Track, TrackMeta

GPX11 = 'xmlns="http://www.topografix.com/GPX/1/1"'
GPX10 = 'xmlns="http://www.topografix.com/GPX/1/0"'
TPX1 = "http://www.garmin.com/xmlschemas/TrackPointExtension/v1"
TPX2 = "http://www.garmin.com/xmlschemas/TrackPointExtension/v2"

# landmarks
CENTRAL_PARK = (40.7812, -73.9665)
HYDE_PARK = (51.5073, -0.1657)
EIFFEL_TOWER = (48.8584, 2.2945)
TORONTO_CITY_HALL = (43.6534, -79.3841)
OPERA_HOUSE = (-33.8568, 151.2153)
MID_ATLANTIC = (30.0, -40.0)


def _utc(*args):
    return dt.datetime(*args, tzinfo=dt.timezone.utc).timestamp()


def _gpx(body, ns=GPX11, version="1.1", extra_ns="", creator="Test Logger"):
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<gpx version="{version}" creator="{creator}" {ns} {extra_ns}>{body}</gpx>'
    )


def test_gpx11_track_with_segments_names_and_elevation():
    text = _gpx(
        f"""
        <trk><name>Park loop</name><type>running</type>
          <trkseg>
            <trkpt lat="{CENTRAL_PARK[0]}" lon="{CENTRAL_PARK[1]}"><ele>40.5</ele>
              <time>2024-05-01T12:00:00Z</time></trkpt>
            <trkpt lat="40.7820" lon="-73.9660"><ele>41</ele><time>2024-05-01T12:00:10Z</time></trkpt>
          </trkseg>
          <trkseg>
            <trkpt lat="40.7830" lon="-73.9650"><ele>42</ele><time>2024-05-01T12:05:00Z</time></trkpt>
          </trkseg>
        </trk>
        <trk><name>Second</name><trkseg>
          <trkpt lat="{HYDE_PARK[0]}" lon="{HYDE_PARK[1]}"><time>2024-05-02T08:00:00Z</time></trkpt>
        </trkseg></trk>"""
    )
    gpx = read_gpx(text)
    assert isinstance(gpx, GpxFile)
    assert len(gpx.tracks) == 2 and gpx.routes == () and gpx.waypoints == () and gpx.skipped == 0
    loop, second = gpx.tracks
    assert len(loop) == 3 and loop.segments == (0, 2)
    assert loop.lat.tolist() == [40.7812, 40.7820, 40.7830]
    assert loop.lon[0] == CENTRAL_PARK[1]
    assert loop.ele.tolist() == [40.5, 41.0, 42.0]
    assert loop.time.tolist() == [_utc(2024, 5, 1, 12), _utc(2024, 5, 1, 12, 0, 10), _utc(2024, 5, 1, 12, 5)]
    assert loop.meta == TrackMeta(name="Park loop", activity="running", device="Test Logger", source="gpx")
    assert loop.columns == ("time", "lat", "lon", "ele")  # absent columns stay absent, not all-NaN
    assert second.meta.name == "Second" and second.meta.activity is None
    assert second.ele is None


def test_gpx10_speed_course_and_satellites():
    text = _gpx(
        f"""<trk><trkseg>
          <trkpt lat="{EIFFEL_TOWER[0]}" lon="{EIFFEL_TOWER[1]}"><ele>35</ele>
            <time>2024-01-01T00:00:00Z</time><course>271.5</course><speed>1.4</speed><sat>9</sat></trkpt>
          <trkpt lat="48.8590" lon="2.2930"><time>2024-01-01T00:00:05Z</time><speed>1.6</speed></trkpt>
        </trkseg></trk>""",
        ns=GPX10,
        version="1.0",
    )
    (t,) = read_gpx(text).tracks
    assert t.speed.tolist() == [1.4, 1.6]
    assert t.heading[0] == 271.5 and math.isnan(t.heading[1])
    assert t.satellites[0] == 9 and math.isnan(t.satellites[1])


def test_file_without_namespace():
    text = (
        '<gpx version="1.1" creator="bare"><trk><trkseg>'
        f'<trkpt lat="{TORONTO_CITY_HALL[0]}" lon="{TORONTO_CITY_HALL[1]}"><ele>90</ele>'
        "<time>2024-03-03T03:03:03Z</time></trkpt>"
        "</trkseg></trk></gpx>"
    )
    (t,) = read_gpx(text).tracks
    assert t.lat[0] == TORONTO_CITY_HALL[0] and t.ele[0] == 90 and t.time[0] == _utc(2024, 3, 3, 3, 3, 3)


@pytest.mark.parametrize(
    ("stamp", "expected"),
    [
        ("2024-06-30T23:59:59Z", _utc(2024, 6, 30, 23, 59, 59)),
        ("2024-06-30T23:59:59.250Z", _utc(2024, 6, 30, 23, 59, 59) + 0.25),
        ("2024-06-30T23:59:59.123456789Z", _utc(2024, 6, 30, 23, 59, 59) + 0.123456789),
        ("2024-07-01T05:29:59+05:30", _utc(2024, 6, 30, 23, 59, 59)),
        ("2024-06-30T19:59:59.5-04:00", _utc(2024, 6, 30, 23, 59, 59) + 0.5),
        ("2024-06-30T19:59:59-0400", _utc(2024, 6, 30, 23, 59, 59)),
        ("2024-06-30T23:59:59", _utc(2024, 6, 30, 23, 59, 59)),  # GPX times are UTC by definition
        ("2024-02-29T12:00:00+00:00", _utc(2024, 2, 29, 12)),
        ("1999-12-31T23:59:60Z", _utc(2000, 1, 1)),  # a leap second rolls into the next minute
        ("not a time", math.nan),
    ],
)
def test_time_formats(stamp, expected):
    text = _gpx(
        f'<trk><trkseg><trkpt lat="{HYDE_PARK[0]}" lon="{HYDE_PARK[1]}"><time>{stamp}</time></trkpt>'
        "</trkseg></trk>"
    )
    got = read_gpx(text).tracks[0].time[0]
    if math.isnan(expected):
        assert math.isnan(got)
    else:
        assert got == pytest.approx(expected, abs=1e-6)


def test_track_without_times_has_nan_times():
    text = _gpx(
        f'<trk><trkseg><trkpt lat="{OPERA_HOUSE[0]}" lon="{OPERA_HOUSE[1]}"/>'
        '<trkpt lat="-33.8570" lon="151.2150"/></trkseg></trk>'
    )
    (t,) = read_gpx(text).tracks
    assert len(t) == 2 and np.isnan(t.time).all()


def test_hdop_is_kept_apart_from_accuracy():
    text = _gpx(
        f'<trk><trkseg><trkpt lat="{EIFFEL_TOWER[0]}" lon="{EIFFEL_TOWER[1]}"><hdop>1.2</hdop></trkpt>'
        '<trkpt lat="48.8590" lon="2.2930"/></trkseg></trk>'
        f'<trk><trkseg><trkpt lat="{HYDE_PARK[0]}" lon="{HYDE_PARK[1]}"/></trkseg></trk>'
    )
    gpx = read_gpx(text)
    assert gpx.tracks[0].accuracy is None  # hdop is a unitless ratio, accuracy is metres
    first, second = gpx.track_hdop
    assert first[0] == 1.2 and math.isnan(first[1])
    assert second is None


def test_garmin_track_point_extensions_and_power():
    text = _gpx(
        f"""<trk><trkseg>
          <trkpt lat="{CENTRAL_PARK[0]}" lon="{CENTRAL_PARK[1]}"><time>2024-05-01T12:00:00Z</time>
            <extensions><power>210</power><gpxtpx:TrackPointExtension>
              <gpxtpx:atemp>21.5</gpxtpx:atemp><gpxtpx:hr>142</gpxtpx:hr><gpxtpx:cad>88</gpxtpx:cad>
            </gpxtpx:TrackPointExtension></extensions></trkpt>
          <trkpt lat="40.7820" lon="-73.9660"><time>2024-05-01T12:00:01Z</time>
            <extensions><tpx2:TrackPointExtension><tpx2:hr>145</tpx2:hr><tpx2:speed>6.5</tpx2:speed>
              <tpx2:course>12.5</tpx2:course></tpx2:TrackPointExtension>
              <pwr:PowerInWatts>230</pwr:PowerInWatts></extensions></trkpt>
        </trkseg></trk>""",
        extra_ns=(
            f'xmlns:gpxtpx="{TPX1}" xmlns:tpx2="{TPX2}" '
            'xmlns:pwr="http://www.garmin.com/xmlschemas/PowerExtension/v1"'
        ),
    )
    (t,) = read_gpx(text).tracks
    assert t.hr.tolist() == [142, 145]
    assert t.cadence[0] == 88 and math.isnan(t.cadence[1])
    assert t.temperature[0] == 21.5
    assert t.power.tolist() == [210, 230]
    assert math.isnan(t.speed[0]) and t.speed[1] == 6.5
    assert t.heading[1] == 12.5


def test_activity_from_type_keywords_and_basicairdata_comment():
    point = f'<trkpt lat="{TORONTO_CITY_HALL[0]}" lon="{TORONTO_CITY_HALL[1]}"/>'
    keywords = _gpx(f"<metadata><keywords>cycling</keywords></metadata><trk><trkseg>{point}</trkseg></trk>")
    assert read_gpx(keywords).tracks[0].meta.activity == "cycling"
    comment = _gpx(
        "<!-- Created with BasicAirData GPS Logger for Android - ver. 3.2.1 -->\n"
        "<!--  Activity = bus -->\n"
        f"<trk><name>Commute</name><trkseg>{point}</trkseg></trk>"
    )
    t = read_gpx(comment).tracks[0]
    assert t.meta.activity == "bus" and t.meta.name == "Commute"
    own_type = _gpx(f"<!-- Activity = bus --><trk><type>walking</type><trkseg>{point}</trkseg></trk>")
    assert read_gpx(own_type).tracks[0].meta.activity == "walking"  # the track's own type wins


def test_metadata_name_is_the_fallback_track_name():
    text = _gpx(
        "<metadata><name>Morning</name></metadata>"
        f'<trk><trkseg><trkpt lat="{HYDE_PARK[0]}" lon="{HYDE_PARK[1]}"/></trkseg></trk>'
    )
    assert read_gpx(text).tracks[0].meta.name == "Morning"


def test_routes_with_and_without_times():
    text = _gpx(
        f"""<rte><name>Harbour walk</name>
          <rtept lat="{OPERA_HOUSE[0]}" lon="{OPERA_HOUSE[1]}"><ele>5</ele><name>Opera House</name></rtept>
          <rtept lat="-33.8523" lon="151.2108"><time>2024-01-01T00:00:00Z</time></rtept>
        </rte>"""
    )
    gpx = read_gpx(text)
    assert gpx.tracks == ()
    (route,) = gpx.routes
    assert route.meta.name == "Harbour walk" and route.segments == (0,)
    assert math.isnan(route.time[0]) and route.time[1] == _utc(2024, 1, 1)
    assert route.ele[0] == 5


def test_waypoints():
    text = _gpx(
        f"""<wpt lat="{EIFFEL_TOWER[0]}" lon="{EIFFEL_TOWER[1]}"><ele>330</ele>
              <time>2024-04-04T10:00:00Z</time><name>Eiffel Tower</name><desc>Top deck</desc></wpt>
            <wpt lat="{MID_ATLANTIC[0]}" lon="{MID_ATLANTIC[1]}"/>"""
    )
    tower, ocean = read_gpx(text).waypoints
    assert tower == Waypoint("Eiffel Tower", *EIFFEL_TOWER, 330.0, _utc(2024, 4, 4, 10), "Top deck")
    assert ocean == Waypoint(None, *MID_ATLANTIC, None, None, None)


def test_invalid_points_are_skipped_and_counted():
    text = _gpx(
        f"""<trk><trkseg>
          <trkpt lat="{CENTRAL_PARK[0]}" lon="{CENTRAL_PARK[1]}"/>
          <trkpt lat="1.2E-5" lon="-73.9665"/>
          <trkpt lat="garbage" lon="-73.9665"/>
          <trkpt lat="0" lon="0.0"/>
          <trkpt lat="95.0" lon="-73.9665"/>
          <trkpt lat="40.7812" lon="-200"/>
          <trkpt lat="nan" lon="-73.9665"/>
          <trkpt lon="-73.9665"/>
          <trkpt lat="40.7820" lon="-73.9660"/>
        </trkseg>
        <trkseg><trkpt lat="0" lon="0"/></trkseg>
        <trkseg><trkpt lat=" 40.7830 " lon="-73.9650"/></trkseg></trk>
        <wpt lat="0" lon="0"><name>Null Island</name></wpt>"""
    )
    gpx = read_gpx(text)
    (t,) = gpx.tracks
    assert t.lat.tolist() == [40.7812, 40.7820, 40.7830]
    assert t.segments == (0, 2)  # the segment whose only point was skipped leaves no empty segment
    assert gpx.waypoints == ()
    assert gpx.skipped == 9


def test_sources_path_bytes_and_str(tmp_path):
    text = _gpx(f'<trk><trkseg><trkpt lat="{HYDE_PARK[0]}" lon="{HYDE_PARK[1]}"/></trkseg></trk>')
    path = tmp_path / "walk.gpx"
    path.write_text(text, encoding="utf-8")
    for source in (path, str(path), text, text.encode()):
        (t,) = read_gpx(source).tracks
        assert t.lat[0] == HYDE_PARK[0]
    assert read_gpx(path).tracks[0].meta.source == "walk.gpx"


def test_latin1_encoded_file():
    text = (
        '<?xml version="1.0" encoding="ISO-8859-1"?>'
        f'<gpx version="1.1" {GPX11}><trk><name>Champs-Élysées</name><trkseg>'
        '<trkpt lat="48.8698" lon="2.3078"/></trkseg></trk></gpx>'
    )
    assert read_gpx(text.encode("latin-1")).tracks[0].meta.name == "Champs-Élysées"


def test_not_gpx_is_an_error():
    with pytest.raises(ValueError, match="GPX"):
        read_gpx("<kml><Document/></kml>")
    with pytest.raises(ValueError, match="XML"):
        read_gpx("<gpx><trk>")


def test_empty_track_element():
    gpx = read_gpx(_gpx("<trk><name>Nothing</name><trkseg/></trk>"))
    (t,) = gpx.tracks
    assert len(t) == 0 and t.meta.name == "Nothing"


def _full_track(n=7, segments=(0, 3, 5)):
    base = _utc(2024, 5, 1, 12)
    lat0, lon0 = CENTRAL_PARK
    rng = np.random.default_rng(1)
    return Track(
        time=base + np.arange(n) * 1.25,  # fractional seconds
        lat=lat0 + np.arange(n) * 1.234567e-4,
        lon=lon0 - np.arange(n) * 7.654321e-5,
        segments=segments,
        meta=TrackMeta(name="Loop & back <1>", activity="cycling"),
        ele=30 + rng.random(n) * 10,
        accuracy=rng.random(n) * 8 + 2,
        speed=rng.random(n) * 9,
        heading=rng.random(n) * 360,
        hr=rng.integers(90, 180, n).astype(float),
        cadence=rng.integers(60, 100, n).astype(float),
        power=rng.integers(100, 300, n).astype(float),
        temperature=np.round(rng.random(n) * 25, 1),
        satellites=rng.integers(4, 14, n).astype(float),
    )


def test_round_trip_keeps_every_column_segment_and_meta(tmp_path):
    original = _full_track()
    other = Track(
        time=[math.nan, math.nan],
        lat=list(OPERA_HOUSE[:1]) * 2,
        lon=[OPERA_HOUSE[1], 151.2160],
        meta=TrackMeta(name="No clock"),
    )
    waypoint = Waypoint("Eiffel Tower", *EIFFEL_TOWER, 330.0, _utc(2024, 4, 4, 10), "Top deck")
    path = tmp_path / "out.gpx"
    text = write_gpx([original, other], path, waypoints=[waypoint])
    assert path.read_text(encoding="utf-8") == text
    gpx = read_gpx(path)
    back, back_other = gpx.tracks
    assert back.columns == original.columns == ("time", "lat", "lon", *OPTIONAL_COLUMNS)
    assert back.segments == original.segments
    assert back.meta.name == original.meta.name and back.meta.activity == "cycling"
    assert back.meta.device == "placewise"
    for column in original.columns:
        np.testing.assert_allclose(getattr(back, column), getattr(original, column), rtol=0, atol=1e-6)
    np.testing.assert_array_equal(back.lat, original.lat)  # coordinates survive exactly
    np.testing.assert_array_equal(back.lon, original.lon)
    assert np.isnan(back_other.time).all() and back_other.columns == ("time", "lat", "lon")
    assert gpx.waypoints == (waypoint,)
    assert gpx.skipped == 0


def test_round_trip_keeps_missing_values_missing():
    t = Track(
        time=[_utc(2024, 1, 1), math.nan, _utc(2024, 1, 1, 0, 0, 2)],
        lat=[HYDE_PARK[0]] * 3,
        lon=[HYDE_PARK[1], -0.1660, -0.1670],
        hr=[120, math.nan, 125],
        ele=[math.nan, 20, math.nan],
    )
    (back,) = read_gpx(write_gpx(t, None)).tracks
    np.testing.assert_array_equal(back.time, t.time)
    np.testing.assert_array_equal(back.hr, t.hr)
    np.testing.assert_array_equal(back.ele, t.ele)


def test_written_xml_is_gpx_11():
    text = write_gpx(_full_track(), None, creator="tester")
    root = ET.fromstring(text)
    assert root.tag == "{http://www.topografix.com/GPX/1/1}gpx"
    assert root.get("version") == "1.1" and root.get("creator") == "tester"
    assert "E-" not in text and "e-" not in text  # xsd:decimal has no exponent
    assert f"{{{TPX2}}}hr" in {e.tag for e in root.iter()}


def test_many_points_stream():
    n = 20_000
    lat = np.linspace(MID_ATLANTIC[0], MID_ATLANTIC[0] + 1, n)
    lon = np.full(n, MID_ATLANTIC[1])
    t = Track(time=_utc(2024, 1, 1) + np.arange(n, dtype=float), lat=lat, lon=lon, segments=(0, n // 2))
    (back,) = read_gpx(write_gpx(t, None).encode()).tracks
    assert len(back) == n and back.segments == (0, n // 2)
    np.testing.assert_array_equal(back.time, t.time)


FIXTURES = Path(__file__).resolve().parents[1] / "data" / "tracks"


@pytest.mark.parametrize(
    ("name", "points"),
    [
        ("ttc_900_airport_express.gpx", 725),
        ("yrt_viva_purple.gpx", 600),
        ("hyderabad_airport_express.gpx", 1800),
        ("hyderabad_bengaluru_highway.gpx", 1800),
    ],
)
def test_real_bus_route_fixtures(name, points):
    gpx = read_gpx(FIXTURES / name)
    assert gpx.skipped == 0
    (t,) = gpx.tracks
    assert len(t) == points and t.segments == (0,)
    # timestamps were shifted into the first days of 2001 when the fixtures were anonymised
    start = dt.datetime.fromtimestamp(t.time[0], dt.timezone.utc)
    assert (
        dt.datetime(2001, 1, 1, tzinfo=dt.timezone.utc)
        <= start
        < dt.datetime(2001, 1, 8, tzinfo=dt.timezone.utc)
    )
    assert np.all(np.diff(t.time) > 0)
    for column in ("ele", "speed", "satellites"):
        assert column in t.columns and np.isfinite(getattr(t, column)).all()
    assert t.meta.activity == "bus"
