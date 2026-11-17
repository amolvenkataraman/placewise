"""placewise.store.archive: checking a pack directory against its pack.json."""

import hashlib
import json

import pytest

from placewise.constants import store as const
from placewise.store import archive


def write_pack(root, files, listed):
    root.mkdir()
    for rel, data in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    doc = {"schema": const.PACK_SCHEMA, "name": "world", "version": "2026.11", "files": listed}
    (root / const.PACK_MANIFEST).write_text(json.dumps(doc))


def damaged_pack(root):
    """40 files; some resized, some rewritten with the same size, some missing, one unlisted."""
    files = {f"layer{i % 4}/col/c{i:02}.npy": bytes([i]) * (1000 + i) for i in range(40)}
    listed = {rel: {"sha256": hashlib.sha256(d).hexdigest(), "size": len(d)} for rel, d in files.items()}
    for i in range(0, 40, 7):
        files[f"layer{i % 4}/col/c{i:02}.npy"] += b"x"  # wrong size
    for i in range(3, 40, 9):
        files[f"layer{i % 4}/col/c{i:02}.npy"] = b"y" * (1000 + i)  # same size, wrong bytes
    for i in (5, 22):
        del files[f"layer{i % 4}/col/c{i:02}.npy"]
    files["layer0/extra.bin"] = b"z"
    write_pack(root, files, listed)


def test_problems_come_in_file_order_however_many_threads_hash(tmp_path, monkeypatch):
    damaged_pack(tmp_path / "world-2026.11")
    found = archive.check_pack_dir(tmp_path / "world-2026.11", "world", "2026.11", "its name")
    monkeypatch.setattr(const, "HASH_THREADS", 1)
    assert archive.check_pack_dir(tmp_path / "world-2026.11", "world", "2026.11", "its name") == found
    assert len(found) == 6 + 5 + 2 + 1 - 1  # c21 is both resized and rewritten: one problem
    assert found[-1] == f"layer0/extra.bin: not listed in {const.PACK_MANIFEST}"
    listed = [p.split(":")[0] for p in found[:-1]]
    assert listed == sorted(listed)
    assert "layer1/col/c05.npy: listed in pack.json but missing" in found
    assert "layer3/col/c03.npy: sha256 doesn't match pack.json" in found
    assert "layer0/col/c00.npy: 1001 bytes, pack.json says 1000" in found


def test_a_read_error_surfaces_as_without_threads(tmp_path, monkeypatch):
    damaged_pack(tmp_path / "world-2026.11")
    real = archive.sha256_file

    def failing(path):
        if path.name in ("c10.npy", "c30.npy"):
            raise PermissionError(f"can't read {path.name}")
        return real(path)

    monkeypatch.setattr(archive, "sha256_file", failing)
    with pytest.raises(PermissionError, match=r"c10\.npy"):  # the first in file order
        archive.check_pack_dir(tmp_path / "world-2026.11", "world", "2026.11", "its name")


@pytest.mark.parametrize("file_digest", [True, False])
def test_sha256_file_with_and_without_file_digest(tmp_path, monkeypatch, file_digest):
    if not file_digest:
        monkeypatch.delattr(hashlib, "file_digest", raising=False)
    elif not hasattr(hashlib, "file_digest"):
        pytest.skip("hashlib.file_digest needs Python 3.11+")
    data = bytes(range(256)) * (const.CHUNK_BYTES // 100)  # more than one chunk
    (tmp_path / "f").write_bytes(data)
    (tmp_path / "empty").write_bytes(b"")
    assert archive.sha256_file(tmp_path / "f") == hashlib.sha256(data).hexdigest()
    assert archive.sha256_file(tmp_path / "empty") == hashlib.sha256(b"").hexdigest()
