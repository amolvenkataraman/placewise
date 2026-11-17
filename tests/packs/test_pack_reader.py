import json
import re

import numpy as np
import pytest
from pack_kit import CREATED, box_feature, e7, fiji, point_layer, polygon_layer

from placewise.model import BBox, Feature, Outline
from placewise.packs import (
    Layer,
    Pack,
    PackFormatError,
    PackIntegrityError,
    PointLayer,
    PolygonLayer,
    open_pack,
    write_pack,
)

ALL_TYPES = {
    "a_i1": np.array([-128, 0, 127], dtype=np.int8),
    "a_i2": np.array([-32768, 0, 32767], dtype=np.int16),
    "a_i4": np.array([-(2**31), 0, 2**31 - 1], dtype=np.int32),
    "a_i8": np.array([-(2**63), 0, 2**63 - 1], dtype=np.int64),
    "a_u1": np.array([0, 1, 255], dtype=np.uint8),
    "a_u2": np.array([0, 1, 65535], dtype=np.uint16),
    "a_u4": np.array([0, 1, 2**32 - 1], dtype=np.uint32),
    "a_f4": np.array([-1.5, 0.0, 3.25], dtype=np.float32),
    "a_f8": np.array([-1e300, np.nan, 1e-300]),
    "a_bool": np.array([True, False, True]),
    "a_str": ["Zürich", "", "東京 🗼"],
}


@pytest.fixture
def pack(tmp_path):
    spots = point_layer([43.6532, -33.8688, 64.1466], [-79.3832, 151.2093, -21.9426], **ALL_TYPES)
    spots.nulls = {"a_i1": -128}
    spots.columns["name"] = ["Toronto", "Sydney", "Reykjavík"]
    spots.columns["code"] = ["CA", "AU", "CA"]
    holed = box_feature(0, 0, 10, 10, (3, 3, 7, 7))
    islands = Feature(outlines=(*box_feature(20, 20, 21, 21).outlines, *box_feature(20, 30, 22, 32).outlines))
    areas = polygon_layer([holed, islands, fiji()], kind_of=["holed", "islands", "fiji"])
    path = write_pack(tmp_path, "test", "2026.11", [spots, areas], created=CREATED)
    return open_pack(path)


def test_pack_attributes(pack):
    assert isinstance(pack, Pack)
    assert (pack.name, pack.version, pack.sources) == ("test", "2026.11", ("synthetic",))
    assert list(pack.layers) == ["spots", "areas"]
    assert isinstance(pack["spots"], PointLayer) and isinstance(pack["areas"], PolygonLayer)
    assert isinstance(pack["spots"], Layer)
    assert "spots" in pack and "nope" not in pack
    with pytest.raises(KeyError, match="nope"):
        pack["nope"]


def test_layer_attributes(pack):
    spots = pack["spots"]
    assert (spots.name, spots.kind, spots.count, spots.sources) == ("spots", "point", 3, ("synthetic",))
    assert spots.fields["a_u2"] == "u2" and spots.fields["id"] == "str" and spots.fields["a_bool"] == "bool"
    assert spots.nulls == {"a_i1": -128}
    assert len(spots) == 3


def test_every_field_type_round_trips(pack):
    spots = pack["spots"]
    for field, values in ALL_TYPES.items():
        column = spots.column(field)
        if field == "a_str":
            assert column.dtype == object and column.tolist() == values
        else:
            assert column.dtype == values.dtype, field
            np.testing.assert_array_equal(column, values)


def test_numeric_columns_are_memory_mapped_and_read_only(pack):
    column = pack["spots"].column("a_i8")
    assert isinstance(column, np.memmap) or isinstance(column.base, np.memmap)
    assert not column.flags.writeable


def test_string_columns_are_cached(pack):
    assert pack["spots"].column("name") is pack["spots"].column("name")


def test_values_and_rows_turn_nulls_into_none(pack):
    spots = pack["spots"]
    assert spots.value("a_i1", 0) is None  # the sentinel
    assert spots.value("a_i1", 2) == 127
    assert spots.value("a_f8", 1) is None  # NaN
    assert spots.value("a_str", 1) is None  # the empty string
    assert spots.value("a_str", 2) == "東京 🗼"
    row = spots.row(2)
    assert row["name"] == "Reykjavík" and row["a_u4"] == 2**32 - 1 and row["a_bool"] is True
    assert type(row["a_i8"]) is int and type(row["a_f4"]) is float
    with pytest.raises(KeyError, match="nope"):
        spots.column("nope")
    with pytest.raises(IndexError):
        spots.row(3)


def test_find(pack):
    spots = pack["spots"]
    assert spots.find("id", "synthetic:spots:1").tolist() == [1]
    assert spots.find("code", "CA").tolist() == [0, 2]
    assert spots.find("code", "ZZ").tolist() == []
    assert spots.find("a_u1", 255).tolist() == [2]
    assert spots.find("a_bool", True).tolist() == [0, 2]


def test_points_come_back_in_degrees(pack):
    spots = pack["spots"]
    assert spots.lat.dtype == np.float64
    np.testing.assert_array_equal(spots.lat, [43.6532, -33.8688, 64.1466])
    np.testing.assert_array_equal(spots.lon, [-79.3832, 151.2093, -21.9426])


def test_features_round_trip_with_holes_and_parts(pack):
    areas = pack["areas"]
    holed = areas.feature(0)
    assert holed == Feature(
        outlines=box_feature(0, 0, 10, 10, (3, 3, 7, 7)).outlines,
        properties=areas.row(0),
        id="synthetic:areas:0",
    )
    assert len(areas.feature(1).outlines) == 2
    assert areas.feature(1).properties["kind_of"] == "islands"
    assert areas.bbox(1) == BBox(20, 20, 22, 32)


def test_antimeridian_feature_round_trips(pack):
    areas = pack["areas"]
    assert areas.bbox(2) == BBox(-19, 170, -16, -170)
    assert areas.bbox(2).crosses_antimeridian
    assert areas.feature(2).outlines == fiji().outlines


def test_open_does_not_touch_the_arrays(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0], [2.0], pop=[5])], created=CREATED)
    (path / "spots" / "col" / "pop.npy").unlink()
    layer = open_pack(path)["spots"]
    assert layer.lat.tolist() == [1.0]
    with pytest.raises(FileNotFoundError):
        layer.column("pop")


def _rewrite_manifest(path, **changes):
    manifest = json.loads((path / "pack.json").read_text())
    manifest.update(changes)
    (path / "pack.json").write_text(json.dumps(manifest))


def test_unknown_schema_is_refused(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0], [2.0])], created=CREATED)
    _rewrite_manifest(path, schema=2)
    with pytest.raises(PackFormatError, match="schema 2"):
        open_pack(path)


def test_not_a_pack(tmp_path):
    with pytest.raises(PackFormatError, match=r"pack\.json"):
        open_pack(tmp_path)
    (tmp_path / "pack.json").write_text("{not json")
    with pytest.raises(PackFormatError, match=r"pack\.json"):
        open_pack(tmp_path)


def test_verify_finds_a_flipped_byte(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0, 2.0], [3.0, 4.0])], created=CREATED)
    open_pack(path).verify()  # a good pack passes
    target = path / "spots" / "geom" / "lon.npy"
    data = bytearray(target.read_bytes())
    data[-1] ^= 0x01
    target.write_bytes(bytes(data))
    pack = open_pack(path)  # verify=False by default: opening stays cheap
    with pytest.raises(PackIntegrityError, match=re.escape("spots/geom/lon.npy")):
        pack.verify()
    with pytest.raises(PackIntegrityError, match=re.escape("spots/geom/lon.npy")):
        open_pack(path, verify=True)


def test_verify_finds_missing_and_resized_files(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0], [3.0])], created=CREATED)
    (path / "spots" / "strings.bin").write_bytes(b"extra")
    with pytest.raises(PackIntegrityError, match=re.escape("spots/strings.bin")):
        open_pack(path).verify()
    (path / "spots" / "strings.bin").unlink()
    with pytest.raises(PackIntegrityError, match=re.escape("spots/strings.bin")):
        open_pack(path).verify()


def test_manifest_paths_may_not_escape_the_pack(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0], [3.0])], created=CREATED)
    _rewrite_manifest(path, files={"../outside": {"sha256": "0" * 64, "size": 0}})
    with pytest.raises(PackIntegrityError, match="outside"):
        open_pack(path).verify()


def test_unknown_layer_kinds_still_give_columns(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([1.0], [3.0])], created=CREATED)
    meta_path = path / "spots" / "layer.json"
    meta = json.loads(meta_path.read_text())
    meta["kind"] = "line"
    meta_path.write_text(json.dumps(meta))
    layer = open_pack(path)["spots"]
    assert type(layer) is Layer and layer.kind == "line"
    assert layer.value("name", 0) == "Spot 0"


def test_empty_layer(tmp_path):
    path = write_pack(tmp_path, "test", "2026.11", [point_layer([], [])], created=CREATED)
    layer = open_pack(path)["spots"]
    assert layer.count == 0 and layer.column("name").tolist() == []
    idx, dist = layer.nearest(1.0, 2.0)
    assert idx == -1 and dist == np.inf


def test_outline_e7_helper_matches_storage():
    # the tests compare against shapes rounded the same way the writer rounds
    assert e7(43.65320004) == 43.6532
    assert Outline((((0, 0), (0, 1), (1, 1)),)).rings[0][1] == (0.0, 1.0)
