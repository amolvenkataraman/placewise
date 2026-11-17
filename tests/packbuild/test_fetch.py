import hashlib
import io
import json
import zipfile

import pytest

from packbuild import fetch as fetch_module
from packbuild.fetch import fetch, unzip


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def fake_urlopen(monkeypatch):
    calls = []

    def urlopen(request, timeout=None):
        calls.append(request)
        return _FakeResponse(b"payload for " + request.full_url.encode())

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", urlopen)
    return calls


def test_downloads_once_and_records_sha256_and_date(tmp_path, fake_urlopen):
    url = "https://example.org/data/file.zip"
    path = fetch(url, tmp_path)
    assert path == tmp_path / "file.zip"
    body = b"payload for " + url.encode()
    assert path.read_bytes() == body
    meta = json.loads(path.with_name("file.zip.json").read_text())
    assert meta["url"] == url
    assert meta["sha256"] == hashlib.sha256(body).hexdigest()
    assert meta["size"] == len(body)
    assert len(meta["retrieved"]) == 10  # YYYY-MM-DD
    assert fetch(url, tmp_path) == path  # cached: no second request
    assert len(fake_urlopen) == 1


def test_refresh_downloads_again(tmp_path, fake_urlopen):
    url = "https://example.org/a.txt"
    fetch(url, tmp_path)
    fetch(url, tmp_path, refresh=True)
    assert len(fake_urlopen) == 2


def test_user_agent_is_generic(tmp_path, fake_urlopen):
    fetch("https://example.org/a.txt", tmp_path)
    assert fake_urlopen[0].get_header("User-agent") == "placewise-build"


def test_failed_download_leaves_nothing_behind(tmp_path, monkeypatch):
    def urlopen(request, timeout=None):
        raise OSError("network down")

    monkeypatch.setattr(fetch_module.urllib.request, "urlopen", urlopen)
    with pytest.raises(OSError):
        fetch("https://example.org/a.txt", tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_unzip_extracts_beside_the_archive_once(tmp_path):
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("inner.txt", "hello")
    out = unzip(archive)
    assert out == tmp_path / "pack"
    assert (out / "inner.txt").read_text() == "hello"
    (out / "inner.txt").write_text("kept")
    assert (unzip(archive) / "inner.txt").read_text() == "kept"  # not re-extracted


def test_unzip_refuses_paths_outside_the_target(tmp_path):
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("../escape.txt", "x")
    with pytest.raises(ValueError, match="outside"):
        unzip(archive)
    assert not (tmp_path / "escape.txt").exists()
