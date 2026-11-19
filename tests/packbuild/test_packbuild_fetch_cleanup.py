"""Raw downloads are deleted once a build succeeds (owner: no duplicate data on disk): exactly the
files and folders that build fetched or extracted, with their sidecars; never out/, never another
build's files; a failed build keeps them for the retry; --keep-downloads keeps them."""

import importlib
import io
import zipfile

import pytest

from packbuild import fetch

URL = "https://example.org/data/raw.zip"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _zip_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("raw.txt", "rows")
    return buf.getvalue()


@pytest.fixture
def web(monkeypatch):
    body = _zip_bytes()
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda request, timeout=None: _Response(body))


@pytest.fixture
def cache(tmp_path):
    root = tmp_path / "cache"
    (root / "out" / "world-2026.11").mkdir(parents=True)
    (root / "out" / "world-2026.11" / "pack.json").write_text("{}")
    (root / "other.zip").write_text("another build's download")
    (root / "other.zip.json").write_text("{}")
    return root


def _args(cache, keep=False):
    return type("Args", (), {"cache_dir": cache, "out": cache / "out", "keep_downloads": keep})()


def _left(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


KEPT = ["other.zip", "other.zip.json", "out", "out/world-2026.11", "out/world-2026.11/pack.json"]


def test_deletes_exactly_what_the_build_fetched_and_extracted(web, cache):
    archive = fetch.fetch(URL, cache)
    folder = fetch.fetch("https://example.org/q/answer.json", cache / "wikidata-x")
    assert (fetch.unzip(archive) / "raw.txt").exists() and folder.exists()
    deleted = fetch.delete_downloads(_args(cache))
    assert {p.name for p in deleted} >= {"raw.zip", "raw.zip.json", "raw", "answer.json", "answer.json.json"}
    assert _left(cache) == KEPT  # the emptied wikidata-x folder goes too


def test_a_file_reused_from_the_cache_is_this_builds_too(web, cache):
    fetch.fetch(URL, cache)  # a failed build's download, kept for the retry ...
    fetch._FETCHED.clear()  # ... and the retry, a new process, finds it cached
    fetch.fetch(URL, cache)
    fetch.delete_downloads(_args(cache))
    assert _left(cache) == KEPT


def test_keep_downloads_keeps_them(web, cache):
    fetch.fetch(URL, cache)
    assert fetch.delete_downloads(_args(cache, keep=True)) == []
    assert (cache / "raw.zip").exists() and (cache / "raw.zip.json").exists()


def test_never_deletes_outside_the_cache_or_inside_out(web, cache, tmp_path):
    elsewhere = fetch.fetch(URL, tmp_path / "elsewhere")  # e.g. --cache-dir changed between calls
    fetch.track(cache / "out" / "world-2026.11")
    fetch.track(cache)
    fetch.delete_downloads(_args(cache))
    assert elsewhere.exists() and _left(cache) == KEPT


def test_add_keep_downloads_flag():
    import argparse

    parser = argparse.ArgumentParser()
    fetch.add_keep_downloads(parser)
    assert parser.parse_args([]).keep_downloads is False
    assert parser.parse_args(["--keep-downloads"]).keep_downloads is True


# every builder's main: (module, build function, extra arguments)
BUILDERS = [
    ("world", "build_world", []),
    ("us", "build_us", []),
    ("us_zip", "build", []),
    ("ca", "build_ca", []),
    ("india", "build_india", []),
    ("water", "build_water", []),
    ("parks", "build", ["world"]),
    ("notable", "build", []),
]


def _fake_build(cache, fail=False):
    def build(*args, **kwargs):
        fetch.fetch(URL, cache)
        if fail:
            raise RuntimeError("the build failed")
        return cache / "out" / "world-2026.11"

    return build


@pytest.mark.parametrize(("name", "func", "extra"), BUILDERS, ids=[b[0] for b in BUILDERS])
def test_every_builder_deletes_its_downloads_after_a_successful_build(
    web, cache, monkeypatch, name, func, extra
):
    module = importlib.import_module(f"packbuild.{name}")
    monkeypatch.setattr(module, func, _fake_build(cache))
    argv = [*extra, "--cache-dir", str(cache), "--out", str(cache / "out"), "--version", "2026.11"]
    module.main(argv)
    assert _left(cache) == KEPT


@pytest.mark.parametrize(("name", "func", "extra"), BUILDERS, ids=[b[0] for b in BUILDERS])
def test_a_failed_build_keeps_its_downloads_for_the_retry(web, cache, monkeypatch, name, func, extra):
    module = importlib.import_module(f"packbuild.{name}")
    monkeypatch.setattr(module, func, _fake_build(cache, fail=True))
    with pytest.raises(RuntimeError):
        module.main([*extra, "--cache-dir", str(cache), "--out", str(cache / "out")])
    assert (cache / "raw.zip").exists() and (cache / "raw.zip.json").exists()


def test_keep_downloads_flag_on_a_builder(web, cache, monkeypatch):
    from packbuild import world

    monkeypatch.setattr(world, "build_world", _fake_build(cache))
    world.main(["--cache-dir", str(cache), "--out", str(cache / "out"), "--keep-downloads"])
    assert (cache / "raw.zip").exists()
