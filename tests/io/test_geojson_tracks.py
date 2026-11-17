"""GeoJSON LineString / MultiLineString tracks, with times from coordTimes (togeojson, Strava),
coordinateProperties.times or a fourth coordinate. Points are around the Serpentine in Hyde Park, London.
GeoJSON positions are (lon, lat)."""

import json

import numpy as np
import pytest

from placewise.io.geojson_tracks import read_geojson_tracks, write_geojson_track
from placewise.tracks import Track, TrackMeta

T0 = 1714564800.0  # 2024-05-01T12:00:00Z

LINE = [[-0.1657, 51.5073, 20.0], [-0.1690, 51.5068, 21.0], [-0.1722, 51.5062, 22.5]]

COLLECTION = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "Serpentine walk",
                "type": "walking",
                "time": "2024-05-01T12:00:00Z",
                "coordTimes": ["2024-05-01T12:00:00Z", "2024-05-01T12:01:00Z", "2024-05-01T12:02:00.250Z"],
            },
            "geometry": {"type": "LineString", "coordinates": LINE},
        },
        {
            "type": "Feature",
            "properties": {"name": "Speakers' Corner"},
            "geometry": {"type": "Point", "coordinates": [-0.1597, 51.5129]},
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Two laps",
                "coordinateProperties": {
                    "times": [
                        ["2024-05-01T12:00:00Z", "2024-05-01T12:00:10Z"],
                        ["2024-05-01T12:30:00Z", "2024-05-01T12:30:10Z", "2024-05-01T12:30:20Z"],
                    ],
                    "heart": [[100, 102], [110, 111, 112]],
                },
            },
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[-0.1657, 51.5073], [-0.1690, 51.5068]],
                    [[-0.1722, 51.5062], [-0.1750, 51.5058], [-0.1780, 51.5055]],
                ],
            },
        },
    ],
}


def test_line_string_with_coord_times():
    walk, _ = read_geojson_tracks(COLLECTION)  # the Point feature is skipped
    assert walk.meta.name == "Serpentine walk" and walk.meta.activity == "walking"
    assert (walk.lat[0], walk.lon[0]) == (51.5073, -0.1657)  # flipped from GeoJSON's (lon, lat)
    assert list(walk.ele) == [20.0, 21.0, 22.5]
    assert list(walk.time) == [T0, T0 + 60, T0 + 120.25]
    assert walk.segments == (0,)


def test_multi_line_string_parts_are_segments_with_coordinate_properties():
    _, laps = read_geojson_tracks(COLLECTION)
    assert laps.meta.name == "Two laps"
    assert len(laps) == 5 and laps.segments == (0, 2)
    assert laps.time[2] == T0 + 1800 and laps.time[4] == T0 + 1820
    assert list(laps.hr) == [100, 102, 110, 111, 112]
    assert laps.ele is None


def test_fourth_coordinate_is_unix_time_and_missing_times_are_nan():
    four = {"type": "LineString", "coordinates": [[-0.1657, 51.5073, 20, T0], [-0.1690, 51.5068, 21, T0 + 5]]}
    (track,) = read_geojson_tracks(four)  # a bare geometry
    assert list(track.time) == [T0, T0 + 5] and list(track.ele) == [20, 21]
    plain = {"type": "Feature", "properties": None, "geometry": {"type": "LineString", "coordinates": LINE}}
    (untimed,) = read_geojson_tracks(plain)
    assert np.all(np.isnan(untimed.time)) and untimed.meta.name is None


def test_numeric_coord_times_in_seconds_or_milliseconds():
    feature = {
        "type": "Feature",
        "properties": {"coordTimes": [T0 * 1000, (T0 + 1) * 1000]},
        "geometry": {"type": "LineString", "coordinates": LINE[:2]},
    }
    (track,) = read_geojson_tracks(feature)
    assert list(track.time) == [T0, T0 + 1]
    feature["properties"]["coordTimes"] = [T0, T0 + 1]
    (track,) = read_geojson_tracks(feature)
    assert list(track.time) == [T0, T0 + 1]


def test_sources_bytes_text_and_path(tmp_path):
    path = tmp_path / "walk.geojson"
    path.write_text(json.dumps(COLLECTION), encoding="utf-8")
    from_path = read_geojson_tracks(path)
    from_bytes = read_geojson_tracks(json.dumps(COLLECTION).encode())
    assert len(from_path) == len(from_bytes) == 2
    assert from_path[0].meta.source == "walk.geojson"
    np.testing.assert_array_equal(from_path[1].lon, from_bytes[1].lon)


def test_not_geojson_is_an_error():
    with pytest.raises(ValueError, match="GeoJSON"):
        read_geojson_tracks({"type": "Topology"})


def test_write_round_trip_single_and_multi_segment():
    single = Track(
        time=T0 + np.array([0.0, 60.0, 120.5]),
        lat=[51.5073, 51.5068, 51.5062],
        lon=[-0.1657, -0.1690, -0.1722],
        meta=TrackMeta(name="Serpentine walk", activity="walking"),
        ele=[20.0, 21.0, 22.5],
    )
    feature = write_geojson_track(single)
    assert feature["type"] == "Feature" and feature["geometry"]["type"] == "LineString"
    assert feature["geometry"]["coordinates"][0] == [-0.1657, 51.5073, 20.0]
    assert feature["properties"]["coordTimes"][2] == "2024-05-01T12:02:00.500Z"
    (back,) = read_geojson_tracks(json.loads(json.dumps(feature)))
    for name in single.columns:
        np.testing.assert_array_equal(getattr(back, name), getattr(single, name))
    assert back.meta.name == "Serpentine walk" and back.meta.activity == "walking"

    multi = Track(
        time=[T0, np.nan, T0 + 1800],
        lat=[51.5073, 51.5068, 51.5062],
        lon=[-0.1657, -0.1690, -0.1722],
        segments=(0, 2),
        hr=[100, np.nan, 110],
    )
    feature = write_geojson_track(multi)
    assert feature["geometry"]["type"] == "MultiLineString"
    assert feature["properties"]["coordTimes"] == [["2024-05-01T12:00:00Z", None], ["2024-05-01T12:30:00Z"]]
    text = json.dumps(feature, allow_nan=False)  # NaN is not JSON; missing values must be null
    (back,) = read_geojson_tracks(text.encode())
    assert back.segments == (0, 2)
    np.testing.assert_array_equal(back.time, multi.time)
    np.testing.assert_array_equal(back.hr, multi.hr)
