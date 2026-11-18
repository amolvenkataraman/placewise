import hashlib
import json

import numpy as np
import pytest
from pack_kit import CREATED, box_feature, fiji, point_layer, polygon_layer, world_grid

from placewise.constants import packs as consts
from placewise.model import Feature, Outline
from placewise.packs import LayerData, open_pack, write_pack
from placewise.packs import writer as writer_module


def _write(tmp_path, *layers, version="2026.11"):
    return write_pack(tmp_path, "test", version, list(layers), created=CREATED)


def _load(path):
    return np.load(path, allow_pickle=False)


def test_pack_json_lists_every_file_with_its_hash_and_size(tmp_path):
    pack = _write(tmp_path, point_layer([1.0, 2.0], [3.0, 4.0]), polygon_layer([box_feature(0, 0, 1, 1)]))
    assert pack == tmp_path / "test-2026.11"
    manifest = json.loads((pack / "pack.json").read_text())
    assert manifest["schema"] == consts.SCHEMA == 1
    assert (manifest["name"], manifest["version"], manifest["created"]) == ("test", "2026.11", CREATED)
    assert manifest["layers"] == ["spots", "areas"]
    assert manifest["sources"] == ["synthetic"]
    on_disk = sorted(p.relative_to(pack).as_posix() for p in pack.rglob("*") if p.is_file())
    assert sorted(manifest["files"]) == [f for f in on_disk if f != "pack.json"]
    for rel, meta in manifest["files"].items():
        data = (pack / rel).read_bytes()
        assert meta == {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
    assert not list(tmp_path.glob(".*"))  # no temporary directory left behind


def test_layer_json_and_the_column_files(tmp_path):
    layer = point_layer(
        [1.0, 2.0, 3.0],
        [4.0, 5.0, 6.0],
        population=[10, 20, 30],
        area=[1.5, 2.5, np.nan],
        capital=[True, False, False],
        tier=np.array([1, -1, 3], dtype=np.int8),
        iso2=["AA", "", "AA"],
    )
    layer.nulls = {"tier": -1}
    pack = _write(tmp_path, layer)
    meta = json.loads((pack / "spots" / "layer.json").read_text())
    assert meta == {
        "name": "spots",
        "kind": "point",
        "count": 3,
        "sources": ["synthetic"],
        "fields": {
            "id": {"type": "str"},
            "name": {"type": "str"},
            "population": {"type": "i8"},
            "area": {"type": "f8"},
            "capital": {"type": "bool"},
            "tier": {"type": "i1", "null": -1},
            "iso2": {"type": "str"},
        },
        "coords": "e7",
    }
    col = pack / "spots" / "col"
    assert _load(col / "population.npy").dtype == np.dtype("<i8")
    assert _load(col / "area.npy").dtype == np.dtype("<f8")
    assert _load(col / "capital.npy").dtype == np.dtype(bool)
    assert _load(col / "tier.npy").tolist() == [1, -1, 3]
    assert _load(col / "iso2.npy").dtype == np.dtype("<i4")


def test_string_table_is_deduplicated_with_the_empty_string_first(tmp_path):
    layer = point_layer([0.0, 1.0, 2.0], [0.0, 1.0, 2.0], iso2=["Zürich", "", "Zürich"])
    layer.columns["name"] = ["東京", "São Paulo", "東京"]
    pack = _write(tmp_path, layer)
    blob = (pack / "spots" / "strings.bin").read_bytes()
    idx = _load(pack / "spots" / "strings.idx.npy")
    assert idx.dtype == np.dtype("<i8") and idx[0] == idx[1] == 0
    table = [blob[idx[k] : idx[k + 1]].decode() for k in range(len(idx) - 1)]
    assert table[0] == "" and len(table) == len(set(table))
    assert {"Zürich", "東京", "São Paulo"} <= set(table)
    iso2 = _load(pack / "spots" / "col" / "iso2.npy")
    assert [table[k] for k in iso2] == ["Zürich", "", "Zürich"]
    assert iso2[1] == 0


def test_points_are_int32_e7(tmp_path):
    pack = _write(tmp_path, point_layer([43.6532, -33.8688], [-79.3832, 151.2093]))
    lat, lon = _load(pack / "spots" / "geom" / "lat.npy"), _load(pack / "spots" / "geom" / "lon.npy")
    assert lat.dtype == lon.dtype == np.dtype("<i4")
    assert lat.tolist() == [436532000, -338688000] and lon.tolist() == [-793832000, 1512093000]


def test_polygon_offsets_holes_multipolygons_and_bbox(tmp_path):
    holed = box_feature(0, 0, 10, 10, (3, 3, 7, 7))
    islands = box_feature(20, 20, 21, 21)
    islands = type(islands)(outlines=(*islands.outlines, *box_feature(20, 30, 22, 32).outlines))
    pack = _write(tmp_path, polygon_layer([holed, islands]))
    geom = pack / "areas" / "geom"
    assert _load(geom / "lat.npy").dtype == np.dtype("<i4")
    assert _load(geom / "ring.npy").tolist() == [0, 4, 8, 12, 16]  # rings stored open: 4 vertices each
    assert _load(geom / "part.npy").tolist() == [0, 2, 3, 4]
    assert _load(geom / "feature.npy").tolist() == [0, 1, 3]
    bbox = _load(geom / "bbox.npy")
    assert bbox.dtype == np.dtype("<i4") and bbox.shape == (2, 4)
    assert (bbox / consts.E7).tolist() == [[0, 0, 10, 10], [20, 20, 22, 32]]


def test_antimeridian_bbox_has_west_greater_than_east_and_both_sides_are_indexed(tmp_path):
    pack = _write(tmp_path, polygon_layer([fiji()]))
    bbox = _load(pack / "areas" / "geom" / "bbox.npy") / consts.E7
    assert bbox.tolist() == [[-19, 170, -16, -170]]
    meta = json.loads((pack / "areas" / "grid" / "meta.json").read_text())
    # cut to the cells the layer reaches: rows -19..-16, columns 170..180 then -180..-170
    assert meta == {"cell_deg": 1.0, "rows": 4, "cols": 21, "row0": 71, "col0": 350}
    _, cell, items, _ = world_grid(pack / "areas" / "grid")

    def candidates(lat, lon):
        k = int((lat + 90) // 1) * 360 + int((lon + 180) // 1)
        return items[cell[k] : cell[k + 1]].tolist()

    assert candidates(-17.5, 175.5) == [0]
    assert candidates(-17.5, -175.5) == [0]
    assert candidates(-17.5, 0.5) == []  # the box doesn't span the world the long way round


def test_grid_candidates_ascend_and_cover_every_bbox(tmp_path):
    features = [box_feature(0, 0, 5, 5), box_feature(2, 2, 3.5, 3.5), box_feature(-1, -1, 1, 1)]
    pack = _write(tmp_path, polygon_layer(features, cell_deg=1.0))
    grid = pack / "areas" / "grid"
    stored = _load(grid / "cell.npy")
    assert stored.dtype == np.dtype("<i8") and _load(grid / "items.npy").dtype == np.dtype("<i4")
    assert json.loads((grid / "meta.json").read_text()) == {
        "cell_deg": 1.0, "rows": 7, "cols": 7, "row0": 89, "col0": 179,
    }  # fmt: skip
    assert stored.shape == (7 * 7 + 1,) and stored[-1] == len(_load(grid / "items.npy"))
    _, cell, items, _ = world_grid(grid)
    k = 92 * 360 + 182  # the cell [2, 3) x [2, 3)
    assert items[cell[k] : cell[k + 1]].tolist() == [0, 1]
    for c in range(180 * 360):
        assert np.all(np.diff(items[cell[c] : cell[c + 1]]) > 0)


def _inside(pack, layer="areas"):
    meta, _, _, inside = world_grid(pack / layer / "grid")
    return inside.reshape(meta["rows"], meta["cols"])


def test_inside_cells_exclude_boundaries_and_holes(tmp_path):
    # a 0..10 square with a 3..7 hole; 1-degree cells
    pack = _write(tmp_path, polygon_layer([box_feature(0, 0, 10, 10, (3, 3, 7, 7))]))
    inside = _inside(pack)
    assert _load(pack / "areas" / "grid" / "inside.npy").dtype == np.dtype("<i4")
    row, col = lambda lat: 90 + lat, lambda lon: 180 + lon
    assert inside[row(1), col(1)] == 0  # wholly inside, touching no edge
    assert inside[row(0), col(5)] == -1  # the outer edge runs along its south side
    assert inside[row(2), col(5)] == -1  # the hole's edge runs along its north side
    assert inside[row(4), col(4)] == -1  # inside the hole: not inside the feature
    assert inside[row(5), col(5)] == -1
    assert inside[row(20), col(20)] == -1  # far away
    assert (inside == 0).sum() == 100 - 36 - 36  # the 10x10 minus its edge ring and the 6x6 around the hole


def test_inside_cells_respect_feature_order(tmp_path):
    big = box_feature(0, 0, 10, 10)
    partial = box_feature(4.5, 4.5, 5.5, 5.5)  # earlier, half-covers four cells
    whole = box_feature(1.5, 1.5, 3.5, 3.5)  # earlier, wholly covers cell [2, 3) x [2, 3)
    pack = _write(tmp_path, polygon_layer([partial, whole, big]))
    inside = _inside(pack)
    assert inside[94, 184] == -1  # big covers it, but an earlier feature takes part of it
    assert inside[92, 182] == 1  # the earlier, wholly covering feature wins
    assert inside[97, 187] == 2


def test_inside_cell_antimeridian(tmp_path):
    pack = _write(tmp_path, polygon_layer([fiji()]))
    inside = _inside(pack)
    assert inside[90 - 18, 180 + 175] == 0
    assert inside[90 - 18, 180 - 175] == 0
    assert inside[90 - 18, 359] == -1  # 179..180 touches the cut edge at 180


def test_a_feature_with_a_hole_inside_one_cell_is_not_inside_there(tmp_path):
    pack = _write(tmp_path, polygon_layer([box_feature(0, 0, 10, 10, (4.2, 4.2, 4.8, 4.8))]))
    assert _inside(pack)[94, 184] == -1  # the hole's edges lie within the cell
    assert _inside(pack)[93, 183] == 0


def test_types_can_be_explicit_and_are_checked(tmp_path):
    layer = point_layer([0.0, 1.0], [0.0, 1.0], small=[1, 2], code=[7, 8])
    layer.types = {"small": "u1", "code": "i2"}
    pack = _write(tmp_path, layer)
    assert _load(pack / "spots" / "col" / "small.npy").dtype == np.dtype("u1")
    assert _load(pack / "spots" / "col" / "code.npy").dtype == np.dtype("<i2")

    bad = point_layer([0.0], [0.0], small=[300])
    bad.types = {"small": "u1"}
    with pytest.raises(ValueError, match="small"):
        write_pack(tmp_path / "b", "test", "2026.11", [bad])
    unknown = point_layer([0.0], [0.0], x=[1])
    unknown.types = {"x": "u8"}
    with pytest.raises(ValueError, match="u8"):
        write_pack(tmp_path / "c", "test", "2026.11", [unknown])


def test_nulls_in_lists(tmp_path):
    layer = point_layer([0.0, 1.0], [0.0, 1.0], tier=[1, None], area=[None, 2.0], iso2=[None, "AB"])
    layer.types = {"tier": "i1"}
    layer.nulls = {"tier": -1}
    pack = _write(tmp_path, layer)
    col = pack / "spots" / "col"
    assert _load(col / "tier.npy").tolist() == [1, -1]
    assert np.isnan(_load(col / "area.npy")[0])
    assert _load(col / "iso2.npy")[0] == 0


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda layer: layer.columns.update(name=["only one"]), "name"),
        (lambda layer: layer.columns.pop("id"), "id"),
        (lambda layer: layer.columns.pop("name"), "name"),
        (lambda layer: layer.columns.update(id=["a", "a"]), "unique"),
        (lambda layer: layer.columns.update(id=["a", ""]), "id"),
        (lambda layer: setattr(layer, "sources", ()), "source"),
        (lambda layer: setattr(layer, "kind", "line"), "kind"),
        (lambda layer: setattr(layer, "lat", None), "lat"),
        (lambda layer: setattr(layer, "lat", np.array([0.0, 91.0])), "lat"),
        (lambda layer: setattr(layer, "name", "../evil"), "name"),
        (lambda layer: layer.columns.update({"bad/field": [1, 2]}), "bad/field"),
        (lambda layer: setattr(layer, "nulls", {"name": -1}), "null"),
    ],
)
def test_layer_validation(tmp_path, mutate, message):
    layer = point_layer([0.0, 1.0], [0.0, 1.0])
    mutate(layer)
    with pytest.raises(ValueError, match=message):
        _write(tmp_path, layer)
    assert list(tmp_path.iterdir()) == []


def test_polygon_validation(tmp_path):
    layer = polygon_layer([box_feature(0, 0, 1, 1)])
    layer.features = []
    with pytest.raises(ValueError, match="features"):
        _write(tmp_path, layer)
    # an edge jumping the antimeridian would make a world-wide sliver; such features must be split
    jumper = LayerData(
        name="areas",
        kind="polygon",
        columns={"id": ["x"], "name": ["x"]},
        sources=("synthetic",),
        features=[Feature(outlines=(Outline((((0, 170), (0, -170), (1, -170), (1, 170)),)),))],
    )
    with pytest.raises(ValueError, match="antimeridian"):
        _write(tmp_path, jumper)
    # +180 to -180 at different latitudes is a jump too, though both ends sit on the antimeridian
    jumper.features = [Feature(outlines=(Outline((((0, 170), (0, 180), (1, -180), (1, 170)),)),))]
    with pytest.raises(ValueError, match="antimeridian"):
        _write(tmp_path, jumper)


def test_a_ring_round_every_longitude(tmp_path):
    # Antarctica-like: down the antimeridian, along the pole's parallel from +180 to -180, back up
    ring = ((-60, -180), (-65, -90), (-60, 0), (-65, 90), (-60, 180), (-90, 180), (-90, -180))
    pack = _write(tmp_path, polygon_layer([Feature(outlines=(Outline((ring,)),))]))
    assert (_load(pack / "areas" / "geom" / "bbox.npy") / consts.E7).tolist() == [[-90, -180, -60, 180]]
    layer = open_pack(pack)["areas"]
    assert layer.query(-80.0, 123.0) == 0 and layer.query(-50.0, 0.0) == -1


@pytest.mark.parametrize("version", ["2026.11", "2026.01", "2026.11.2", "2026.12.10"])
def test_versions_accepted(tmp_path, version):
    assert _write(tmp_path, point_layer([0.0], [0.0]), version=version).name == f"test-{version}"


@pytest.mark.parametrize(
    "version", ["2026.13", "2026.00", "26.11", "2026.1", "2026-11", "2026.11.", "v2026.11"]
)
def test_versions_refused(tmp_path, version):
    with pytest.raises(ValueError, match="version"):
        _write(tmp_path, point_layer([0.0], [0.0]), version=version)


def test_duplicate_layer_names_and_empty_packs_are_refused(tmp_path):
    with pytest.raises(ValueError, match="spots"):
        _write(tmp_path, point_layer([0.0], [0.0]), point_layer([1.0], [1.0]))
    with pytest.raises(ValueError, match="layer"):
        _write(tmp_path)


def test_denied_sources_are_refused(tmp_path):
    layer = point_layer([0.0], [0.0])
    layer.sources = ("gadm",)
    with pytest.raises(ValueError, match="gadm"):
        _write(tmp_path, layer)


def test_failed_write_leaves_nothing_behind(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(writer_module, "_write_grid", explode)
    with pytest.raises(RuntimeError, match="disk on fire"):
        _write(tmp_path, point_layer([0.0], [0.0]), polygon_layer([box_feature(0, 0, 1, 1)]))
    assert list(tmp_path.iterdir()) == []


def test_an_existing_pack_is_never_overwritten(tmp_path):
    first = _write(tmp_path, point_layer([0.0], [0.0]))
    before = (first / "pack.json").read_bytes()
    with pytest.raises(FileExistsError):
        _write(tmp_path, point_layer([1.0], [1.0]))
    assert (first / "pack.json").read_bytes() == before
    assert [p.name for p in tmp_path.iterdir()] == ["test-2026.11"]


def test_same_input_same_bytes(tmp_path):
    def build(where):
        return _write(
            where, point_layer([1.0, 2.0], [3.0, 4.0]), polygon_layer([fiji(), box_feature(0, 0, 9, 9)])
        )

    a, b = build(tmp_path / "a"), build(tmp_path / "b")
    assert (a / "pack.json").read_bytes() == (b / "pack.json").read_bytes()
