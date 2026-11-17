import hashlib
import json
import tarfile

import pytest
from pack_kit import CREATED, box_feature, fiji, point_layer, polygon_layer

from placewise.model import PackInfo
from placewise.packs import archive, open_pack, pack_info, write_index, write_pack


def _build(where, name="test", version="2026.11"):
    layers = [point_layer([1.0, 2.0], [3.0, 4.0]), polygon_layer([fiji(), box_feature(0, 0, 9, 9)])]
    return write_pack(where, name, version, layers, created=CREATED)


def test_archive_is_a_deterministic_tar_xz(tmp_path):
    a, b = _build(tmp_path / "a"), _build(tmp_path / "b")
    (b / "pack.json").touch()  # different mtimes must not matter
    ta, tb = archive(a), archive(b)
    assert ta == tmp_path / "a" / "test-2026.11.tar.xz"
    assert ta.read_bytes() == tb.read_bytes()
    with tarfile.open(ta, "r:xz") as tar:
        members = tar.getmembers()
    names = [m.name for m in members]
    assert names == sorted(names) and names[0] == "test-2026.11"
    assert "test-2026.11/pack.json" in names and "test-2026.11/areas/grid/inside.npy" in names
    assert all(m.mtime == 0 and m.uid == 0 and m.gid == 0 and m.uname == m.gname == "" for m in members)
    assert all(m.isfile() or m.isdir() for m in members)


def test_archive_unpacks_to_a_valid_pack(tmp_path):
    tar_path = archive(_build(tmp_path / "src"))
    with tarfile.open(tar_path, "r:xz") as tar:
        tar.extractall(tmp_path / "out", filter="data")
    pack = open_pack(tmp_path / "out" / "test-2026.11", verify=True)
    assert pack["areas"].query(-17.5, -175) == 0


def test_pack_info_hashes_the_archive(tmp_path):
    tar_path = archive(_build(tmp_path))
    info = pack_info(tar_path)
    assert isinstance(info, PackInfo)
    assert (info.name, info.version, info.schema, info.sources) == ("test", "2026.11", 1, ("synthetic",))
    data = tar_path.read_bytes()
    assert info.sha256 == hashlib.sha256(data).hexdigest() and info.size_bytes == len(data)


def test_write_index(tmp_path):
    infos = [pack_info(archive(_build(tmp_path, name))) for name in ("world", "can")]
    path = write_index(tmp_path, infos)
    assert path == tmp_path / "index.json"
    index = json.loads(path.read_text())
    assert index["schema"] == 1
    assert list(index["packs"]) == ["can", "world"]  # sorted, so the same release gives the same bytes
    entry = index["packs"]["world"]
    assert entry == {
        "version": "2026.11",
        "schema": 1,
        "url": "world-2026.11.tar.xz",
        "sha256": infos[0].sha256,
        "size_bytes": infos[0].size_bytes,
        "sources": ["synthetic"],
    }
    with pytest.raises(ValueError, match="world"):
        write_index(tmp_path, [infos[0], infos[0]])


def test_archive_is_xz_with_literal_coding_for_four_byte_values(tmp_path):
    import lzma

    from placewise.constants import packs as consts

    tar_path = archive(_build(tmp_path))
    data = tar_path.read_bytes()
    filters = [{"id": lzma.FILTER_LZMA2, "preset": 9, "lc": 0, "lp": 2, "pb": 2}]
    assert consts.ARCHIVE_LZMA2 == {"preset": 9, "lc": 0, "lp": 2, "pb": 2}
    assert lzma.compress(lzma.decompress(data), format=lzma.FORMAT_XZ, filters=filters) == data
