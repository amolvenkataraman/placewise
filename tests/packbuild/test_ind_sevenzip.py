"""The minimal 7z reader for the LGD monthly archives: real archives written by 7-Zip 16.02
(base64 below), with an LZMA2 solid block and a compressed header, and with LZMA and a plain one."""

import base64

import pytest

from packbuild.ind import sevenzip

# 7z a -mx=9 a.7z t.01Oct2026.csv t.31Oct2026.csv empty.txt   (LZMA2, solid, encoded header)
LZMA2 = base64.b64decode(
    "N3q8ryccAAQSLOUergAAAAAAAAAhAAAAAAAAAABCxDDgADwAMF0AKYuFxzG/22snZgBxwCguHF/PqO8sJzE+IpJTMQmp7H8S"
    "LvvUyAOK11elarh1Yw0AAAAAgTMHrg/ReeggoJCgd17FQBiQ1qAnuuDd3CrW8HoMRhi00TGLMyI4GKFv4yQG/QMCfgOfkjhZ"
    "pb5IwQPY8n082uJB8qNIfviDyT+hRMKjFj9e9JnzKxiJpV80/i5GbvHTwmGeSLpcTRPUNcAaPLFzGe3IAAAXBjgBCXYABwsB"
    "AAEjAwEBBV0AEAAADICyCgF6w1viAAA="
)
# 7z a -m0=LZMA -mhc=off b.7z t.31Oct2026.csv t.01Oct2026.csv   (LZMA, plain header)
LZMA = base64.b64decode(
    "N3q8ryccAARSL62wMQAAAAAAAACWAAAAAAAAACuJJwoAKYuFxzG/22snZgBxwCguHF/PqO8sJzE+IpJTMQmp7H8SLvvUyAOK"
    "11elarh1Yw0AAQQGAAEJMQAHCwEAASMDAQEFXQAQAAAMPQAIDQIJGQoBR3PHCgwA1TgAAAUCEUEAdAAuADAAMQBPAGMAdAAy"
    "ADAAMgA2AC4AYwBzAHYAAAB0AC4AMwAxAE8AYwB0ADIAMAAyADYALgBjAHMAdgAAABkCAAAUEgEAgFfv1d923QGAV+/V33bd"
    "ARUKAQAggLSBIIC0gQAA"
)
OLD = b"S.No.,Code,Name\n1,10,Old\n"
NEW = b"S.No.,Code,Name\n1,10,New\n2,11,Other\n"


@pytest.fixture(params=["lzma2", "lzma"])
def archive(request, tmp_path):
    path = tmp_path / f"{request.param}.7z"
    path.write_bytes(LZMA2 if request.param == "lzma2" else LZMA)
    return path


def test_lists_members_with_sizes(archive):
    members = {m.name: m.size for m in sevenzip.members(archive)}
    assert members["t.01Oct2026.csv"] == len(OLD) and members["t.31Oct2026.csv"] == len(NEW)


def test_reads_each_member(archive):
    assert sevenzip.read(archive, "t.01Oct2026.csv") == OLD
    assert sevenzip.read(archive, "t.31Oct2026.csv") == NEW


def test_empty_member_and_missing_member(tmp_path):
    path = tmp_path / "a.7z"
    path.write_bytes(LZMA2)
    assert sevenzip.read(path, "empty.txt") == b""
    with pytest.raises(KeyError, match=r"nope\.csv"):
        sevenzip.read(path, "nope.csv")


def test_streams_in_small_chunks(archive, monkeypatch):
    monkeypatch.setattr(sevenzip, "_CHUNK", 3)
    assert sevenzip.read(archive, "t.31Oct2026.csv") == NEW


def test_newest_daily_member(archive):
    assert sevenzip.newest(archive) == "t.31Oct2026.csv"


def test_extract_newest_once(archive, tmp_path):
    out = sevenzip.extract_newest(archive, tmp_path / "out")
    assert out.name == "t.31Oct2026.csv" and out.read_bytes() == NEW
    out.write_bytes(b"cached")  # a second call reuses the extracted copy
    assert sevenzip.extract_newest(archive, tmp_path / "out").read_bytes() == b"cached"


def test_refuses_what_it_cannot_read(tmp_path):
    bad = tmp_path / "bad.7z"
    bad.write_bytes(b"PK\x03\x04 not a 7z archive")
    with pytest.raises(ValueError, match="not a 7z archive"):
        sevenzip.members(bad)
    corrupt = tmp_path / "corrupt.7z"
    data = bytearray(LZMA)
    data[40] ^= 0xFF  # inside the packed stream
    corrupt.write_bytes(bytes(data))
    with pytest.raises(ValueError, match="CRC"):
        sevenzip.read(corrupt, "t.31Oct2026.csv")
