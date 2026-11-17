"""placewise.store.index: fetching, parsing, mirroring and caching the pack index, and offline use.
No network: packs are served from file:// URLs."""

import json

import pytest
from store_kit import make_store

from placewise.model import DataSettings, PackInfo
from placewise.store import DownloadError, OfflineError, PackNotInstalled, Store, StoreError


def test_fetch_index_returns_pack_infos_and_caches_with_absolute_urls(data_dir, release):
    release.add("world", "2026.11")
    release.add("ca", "2026.10")
    store = make_store(data_dir, release)
    index = store.fetch_index()
    assert set(index) == {"world", "ca"}
    world = index["world"]
    assert isinstance(world, PackInfo)
    assert (world.name, world.version, world.schema) == ("world", "2026.11", 1)
    assert world.sources == ("naturalearth",)
    assert store.available() == index
    cached = json.loads((data_dir / "index.json").read_text())
    assert cached["packs"]["world"]["url"] == (release.root / "world-2026.11.tar.xz").as_uri()


@pytest.mark.parametrize(
    "doc",
    [
        {"schema": 2, "packs": {}},
        {"packs": {}},
        {"schema": 1, "packs": []},
        {"schema": 1, "packs": {"world": {"version": "2026.11"}}},
        {
            "schema": 1,
            "packs": {
                "../evil": {
                    "version": "2026.11",
                    "schema": 1,
                    "url": "x",
                    "sha256": "a" * 64,
                    "size_bytes": 1,
                }
            },
        },
        {
            "schema": 1,
            "packs": {
                "world": {"version": "../11", "schema": 1, "url": "x", "sha256": "a" * 64, "size_bytes": 1}
            },
        },
        {
            "schema": 1,
            "packs": {
                "world": {"version": "2026.11", "schema": 1, "url": "x", "sha256": "nothex", "size_bytes": 1}
            },
        },
        ["not", "an", "object"],
    ],
)
def test_malformed_index_is_refused(data_dir, release, doc):
    release.write(doc)
    with pytest.raises(StoreError, match="index"):
        make_store(data_dir, release).fetch_index()
    assert not (data_dir / "index.json").exists()


def test_index_that_is_not_json_is_refused(data_dir, release):
    (release.root / "index.json").write_text("<html>captive portal</html>")
    with pytest.raises(StoreError, match="index"):
        make_store(data_dir, release).fetch_index()


def test_unknown_index_keys_are_ignored(data_dir, release):
    release.add("world", "2026.11")
    release.packs["world"]["future_field"] = 1
    release.write({"schema": 1, "packs": release.packs, "generated": "2026-11-17"})
    assert "world" in make_store(data_dir, release).fetch_index()


def test_mirrors_are_tried_in_order_and_relative_urls_follow_the_mirror(data_dir, release, tmp_path):
    release.add("world", "2026.11")
    missing = (tmp_path / "gone" / "index.json").as_uri()
    mirror_dir = release.root.as_uri() + "/"  # a mirror given as a directory gets index.json appended
    store = Store(data_dir, DataSettings(mirrors=(missing, mirror_dir)), index_url=missing)
    store.fetch_index()
    assert store.install("world").name == "world-2026.11"


def test_all_index_sources_failing_names_each(data_dir, tmp_path):
    a, b = (tmp_path / "a" / "index.json").as_uri(), (tmp_path / "b" / "index.json").as_uri()
    with pytest.raises(DownloadError) as err:
        Store(data_dir, DataSettings(mirrors=(b,)), index_url=a).fetch_index()
    assert a in str(err.value) and b in str(err.value)


def test_relative_and_absolute_pack_urls(data_dir, release, tmp_path):
    release.add("world", "2026.11")
    files = tmp_path / "files"
    files.mkdir()
    (release.root / "world-2026.11.tar.xz").rename(files / "world-2026.11.tar.xz")
    release.packs["world"]["url"] = "../files/world-2026.11.tar.xz"
    release.write()
    assert make_store(data_dir, release).install("world").is_dir()

    release.packs["world"]["url"] = (files / "world-2026.11.tar.xz").as_uri()
    release.write()
    other = tmp_path / "other-data"
    assert make_store(other, release).install("world").is_dir()


def test_unsupported_url_scheme_is_refused(data_dir, release):
    release.add("world", "2026.11", url="ftp://example.invalid/world.tar.xz")
    with pytest.raises(DownloadError, match="scheme"):
        make_store(data_dir, release).install("world")


def test_offline_uses_the_cached_index(data_dir, release):
    release.add("world", "2026.11")
    make_store(data_dir, release).fetch_index()
    (release.root / "index.json").unlink()  # the network is gone
    offline = make_store(data_dir, release, offline=True)
    assert offline.fetch_index()["world"].version == "2026.11"
    assert offline.available()["world"].version == "2026.11"


def test_offline_without_a_cache_is_a_clear_error(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release, offline=True)
    with pytest.raises(OfflineError, match="offline"):
        store.fetch_index()
    with pytest.raises(OfflineError):
        store.install("world")
    with pytest.raises(PackNotInstalled, match="world"):
        store.ensure("world")
    assert not (data_dir / "packs").exists() or not any((data_dir / "packs").iterdir())


def test_offline_ensure_returns_an_installed_pack(data_dir, release):
    release.add("world", "2026.11")
    path = make_store(data_dir, release).install("world")
    (release.root / "index.json").unlink()
    assert make_store(data_dir, release, offline=True).ensure("world") == path
