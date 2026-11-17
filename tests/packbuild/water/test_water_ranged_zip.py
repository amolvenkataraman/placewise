"""packbuild.sources.water.ranged_zip: members of a remote zip, fetched by HTTP range requests."""

import zipfile

import pytest

from packbuild.sources.water import ranged_zip


def _archive(path):
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("dir/", "")
        z.writestr("dir/big.bin", bytes(range(256)) * 4000)  # 1,024,000 bytes
        z.writestr("dir/small.txt", "hello water\n")
        z.writestr("stored.txt", "plain", compress_type=zipfile.ZIP_STORED)
    return path


@pytest.fixture
def remote(tmp_path):
    """An opener reading byte ranges of a local file, counting the bytes it hands out."""
    path = _archive(tmp_path / "remote.zip")
    data = path.read_bytes()
    served = []

    def opener(url, first, last):
        assert url == "https://example.org/remote.zip"
        start = len(data) + first if first < 0 else first
        stop = len(data) if last is None else last + 1
        served.append(stop - start)
        chunk = data[start:stop]
        return iter([chunk[i : i + 1000] for i in range(0, len(chunk), 1000)]), len(data)

    return ranged_zip.RemoteZip("https://example.org/remote.zip", opener=opener), served, len(data)


def test_members_come_from_the_central_directory(remote):
    z, served, _size = remote
    members = z.members()
    assert set(members) == {"dir/", "dir/big.bin", "dir/small.txt", "stored.txt"}
    assert members["dir/big.bin"].size == 1_024_000
    assert sum(served) < 70_000  # only the archive's tail was read


def test_extract_a_whole_member_and_a_prefix_of_one(remote, tmp_path):
    z, served, _size = remote
    assert z.extract("dir/small.txt", tmp_path / "small.txt").read_text() == "hello water\n"
    assert z.extract("stored.txt", tmp_path / "stored.txt").read_text() == "plain"
    served.clear()
    out = z.extract("dir/big.bin", tmp_path / "head.bin", limit=1000)
    assert out.read_bytes() == (bytes(range(256)) * 4)[:1000]
    assert sum(served) < 20_000  # the compressed stream was read only as far as needed


def test_unknown_members_fail(remote, tmp_path):
    z, _, _ = remote
    with pytest.raises(KeyError, match="nope"):
        z.extract("nope", tmp_path / "x")
