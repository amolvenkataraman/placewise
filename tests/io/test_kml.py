"""KML and KMZ tracks: gx:Track, gx:MultiTrack and LineString. The gx:Track fixture follows the KML
reference's example (parallel <when>/<gx:coord> plus ExtendedData arrays); points are in Golden Gate
Park, San Francisco, and on the Embarcadero.
"""

import io
import warnings
import zipfile

import numpy as np
import pytest

from placewise.io._track_common import TrackReadWarning
from placewise.io.kml import read_kml

T0 = 1275012129.0  # 2010-05-28T02:02:09Z, the KML reference example's first <when>

GX_TRACK = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
<Document>
  <name>GPS device</name>
  <Schema id="schema">
    <gx:SimpleArrayField name="heartrate" type="int"><displayName>Heart</displayName></gx:SimpleArrayField>
    <gx:SimpleArrayField name="cadence" type="int"><displayName>Cadence</displayName></gx:SimpleArrayField>
    <gx:SimpleArrayField name="power" type="float"><displayName>Power</displayName></gx:SimpleArrayField>
  </Schema>
  <Folder>
    <name>Tracks</name>
    <Placemark>
      <name>Park ride</name>
      <gx:Track>
        <altitudeMode>absolute</altitudeMode>
        <when>2010-05-28T02:02:09Z</when>
        <when>2010-05-28T02:02:35Z</when>
        <when>2010-05-28T02:02:44.5Z</when>
        <gx:coord>-122.4862 37.7694 52.0</gx:coord>
        <gx:coord>-122.4850 37.7697 53.5</gx:coord>
        <gx:coord>-122.4838 37.7700 55.0</gx:coord>
        <ExtendedData>
          <SchemaData schemaUrl="#schema">
            <gx:SimpleArrayData name="cadence">
              <gx:value>86</gx:value><gx:value>103</gx:value><gx:value>108</gx:value>
            </gx:SimpleArrayData>
            <gx:SimpleArrayData name="heartrate">
              <gx:value>181</gx:value><gx:value>177</gx:value><gx:value>175</gx:value>
            </gx:SimpleArrayData>
            <gx:SimpleArrayData name="power">
              <gx:value>327.0</gx:value><gx:value>177.0</gx:value><gx:value>179.0</gx:value>
            </gx:SimpleArrayData>
          </SchemaData>
        </ExtendedData>
      </gx:Track>
    </Placemark>
    <Placemark>
      <name>A marker, not a track</name>
      <Point><coordinates>-122.4662,37.7715,0</coordinates></Point>
    </Placemark>
  </Folder>
</Document>
</kml>
"""

MULTI_TRACK = """<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2">
<Placemark>
  <name>Two legs</name>
  <gx:MultiTrack>
    <altitudeMode>clampToGround</altitudeMode>
    <gx:interpolate>0</gx:interpolate>
    <gx:Track>
      <when>2010-05-28T02:02:09Z</when><when>2010-05-28T02:02:19Z</when>
      <gx:coord>-122.4862 37.7694 0</gx:coord><gx:coord>-122.4850 37.7697 0</gx:coord>
    </gx:Track>
    <gx:Track>
      <when>2010-05-28T02:10:09Z</when>
      <gx:coord>-122.4700 37.7710</gx:coord>
    </gx:Track>
  </gx:MultiTrack>
</Placemark>
</kml>
"""

LINES = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <Placemark>
    <name>Embarcadero</name>
    <LineString>
      <tessellate>1</tessellate>
      <coordinates>
        -122.3937,37.7955,0 -122.3963,37.7990,0
        -122.4025,37.8060,0
      </coordinates>
    </LineString>
  </Placemark>
  <Placemark>
    <name>Split path</name>
    <MultiGeometry>
      <LineString><coordinates>-122.4862,37.7694 -122.4850,37.7697</coordinates></LineString>
      <LineString>
        <coordinates>-122.4700,37.7710 -122.4690,37.7712 -122.4680,37.7714</coordinates>
      </LineString>
    </MultiGeometry>
  </Placemark>
</Document>
</kml>
"""


def test_gx_track_times_coords_and_extended_data():
    (track,) = read_kml(GX_TRACK.encode())
    assert track.meta.name == "Park ride"
    assert len(track) == 3 and track.segments == (0,)
    assert track.time[0] == T0 and track.time[1] == T0 + 26 and track.time[2] == T0 + 35.5
    assert (track.lat[0], track.lon[0], track.ele[0]) == (37.7694, -122.4862, 52.0)  # coord is lon lat alt
    assert list(track.hr) == [181, 177, 175]
    assert list(track.cadence) == [86, 103, 108]
    assert list(track.power) == [327, 177, 179]


def test_multitrack_parts_are_segments():
    (track,) = read_kml(MULTI_TRACK.encode())
    assert track.meta.name == "Two legs"
    assert len(track) == 3 and track.segments == (0, 2)
    assert track.time[2] == T0 + 480
    assert track.ele[0] == 0 and np.isnan(track.ele[2])  # a 2D coord has no altitude


def test_linestrings_have_no_times_and_multigeometry_parts_are_segments():
    embarcadero, split = read_kml(LINES.encode())
    assert embarcadero.meta.name == "Embarcadero" and len(embarcadero) == 3
    assert np.all(np.isnan(embarcadero.time))
    assert embarcadero.lat[2] == 37.8060 and embarcadero.lon[2] == -122.4025
    assert split.segments == (0, 2) and len(split) == 5
    assert split.ele is None


def test_kmz_from_bytes_and_path(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("files/icon.png", b"\x89PNG not really")
        archive.writestr("doc.kml", GX_TRACK)
    data = buffer.getvalue()
    (track,) = read_kml(data)
    assert track.meta.name == "Park ride" and len(track) == 3
    path = tmp_path / "ride.kmz"
    path.write_bytes(data)
    (from_path,) = read_kml(path)
    assert from_path.meta.source == "ride.kmz"
    np.testing.assert_array_equal(from_path.lat, track.lat)


def test_older_namespace_and_none():
    old = LINES.replace("http://www.opengis.net/kml/2.2", "http://earth.google.com/kml/2.1")
    bare = LINES.replace(' xmlns="http://www.opengis.net/kml/2.2"', "")
    assert len(read_kml(old.encode())) == 2
    assert len(read_kml(bare.encode())) == 2


def test_mismatched_when_and_coord_counts_skip_that_track():
    broken = MULTI_TRACK.replace("<when>2010-05-28T02:10:09Z</when>", "")
    with pytest.warns(TrackReadWarning, match="gx:Track") as caught:
        (track,) = read_kml(broken.encode())
    assert caught[0].message.skipped == 1
    assert len(track) == 2 and track.segments == (0,)


def test_clean_file_reads_without_warnings_and_non_kml_is_an_error():
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        read_kml(GX_TRACK.encode())
    with pytest.raises(ValueError, match="KML"):
        read_kml(b"<gpx></gpx>")
    with pytest.raises(ValueError, match="well-formed"):
        read_kml(GX_TRACK[:300].encode())
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", "no kml here")
    with pytest.raises(ValueError, match="KMZ"):
        read_kml(buffer.getvalue())
