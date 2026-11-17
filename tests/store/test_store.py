"""The pack store: index, install, verification, updates and housekeeping. No network: packs are served
from file:// URLs and, for the HTTP paths, a server on 127.0.0.1."""

import json
import os
import re
import tarfile
import threading
import time

import pytest
from store_kit import (
    LocalServer,
    Release,
    dir_entry,
    file_entry,
    pack_entries,
    pack_json,
    sha256,
    special_entry,
)

import placewise
from placewise.constants import store as store_constants
from placewise.model import DataSettings, PackInfo
from placewise.store import (
    DownloadError,
    IntegrityError,
    LockError,
    OfflineError,
    PackNotInstalled,
    Store,
    StoreError,
    UnsupportedSchemaError,
)


def make_store(data_dir, release, **settings):
    return Store(data_dir, DataSettings(**settings), index_url=release.index_url)


def leftovers(data_dir):
    """Anything in packs/ that isn't a finished pack: temp dirs, partial downloads."""
    packs = data_dir / "packs"
    return sorted(p.name for p in packs.iterdir() if p.name.startswith(".")) if packs.exists() else []


# -- index ----------------------------------------------------------------------------------------


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


def test_index_url_comes_from_argument_then_settings_then_env(data_dir, release, monkeypatch):
    release.add("world", "2026.11")
    assert Store(data_dir, DataSettings(index_url=release.index_url)).index_url == release.index_url
    monkeypatch.setenv("PLACEWISE_INDEX_URL", release.index_url)
    assert Store(data_dir).index_url == release.index_url
    assert (
        Store(data_dir, index_url="file:///elsewhere/index.json").index_url == "file:///elsewhere/index.json"
    )
    monkeypatch.delenv("PLACEWISE_INDEX_URL")
    assert Store(data_dir).index_url == store_constants.DEFAULT_INDEX_URL


def test_default_index_url_and_user_agent_are_generic():
    assert store_constants.DEFAULT_INDEX_URL.startswith("https://")
    assert (
        store_constants.USER_AGENT.format(version=placewise.__version__)
        == f"placewise/{placewise.__version__}"
    )


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


# -- offline --------------------------------------------------------------------------------------


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


# -- install --------------------------------------------------------------------------------------


def test_install_unpacks_into_packs_and_becomes_current(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    path = store.install("world")
    assert path == data_dir / "packs" / "world-2026.11"
    assert json.loads((path / "pack.json").read_text())["name"] == "world"
    assert (path / "countries" / "col" / "id.npy").read_bytes().startswith(b"\x93NUMPY")
    assert store.installed() == {"world": ["2026.11"]}
    assert store.current("world") == path
    assert store.verify() == []
    assert leftovers(data_dir) == []


def test_install_is_idempotent_and_does_not_download_again(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    first = store.install("world")
    (release.root / "world-2026.11.tar.xz").unlink()  # a second download would fail
    assert store.install("world") == first
    assert store.install("world", version="2026.11") == first


def test_install_repairs_a_damaged_installed_copy(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    path = store.install("world")
    (path / "countries" / "layer.json").write_text("tampered")
    assert store.install("world") == path
    assert store.verify() == []
    assert leftovers(data_dir) == []


def test_install_reports_progress(data_dir, release):
    release.add("world", "2026.11")
    calls = []
    make_store(data_dir, release).install("world", progress=lambda done, total: calls.append((done, total)))
    size = release.packs["world"]["size_bytes"]
    assert calls and calls[-1] == (size, size)
    assert [d for d, _ in calls] == sorted(d for d, _ in calls)


def test_install_unknown_pack_or_version(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    with pytest.raises(StoreError, match="nowhere"):
        store.install("nowhere")
    with pytest.raises(StoreError, match=r"2026\.11"):
        store.install("world", version="2025.01")


def test_ensure_installs_on_first_use(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    path = store.ensure("world")
    assert path.name == "world-2026.11"
    assert store.ensure("world") == path


# -- integrity ------------------------------------------------------------------------------------


def assert_refused(data_dir, release, match, exc=IntegrityError):
    store = make_store(data_dir, release)
    with pytest.raises(exc, match=match):
        store.install("world")
    assert store.installed() == {}
    assert leftovers(data_dir) == []


def test_archive_sha_mismatch(data_dir, release):
    release.add("world", "2026.11", sha="0" * 64)
    assert_refused(data_dir, release, "sha256")


def test_file_sha_mismatch(data_dir, release):
    files = {"a.bin": b"real"}
    listed = {"a.bin": {"sha256": sha256(b"fake"), "size": 4}}
    release.add("world", "2026.11", files=files, listed=listed)
    assert_refused(data_dir, release, "a.bin")


def test_file_size_mismatch(data_dir, release):
    files = {"a.bin": b"real"}
    listed = {"a.bin": {"sha256": sha256(b"real"), "size": 5}}
    release.add("world", "2026.11", files=files, listed=listed)
    assert_refused(data_dir, release, "a.bin")


def test_extra_unlisted_file(data_dir, release):
    entries = [*pack_entries("world", "2026.11"), file_entry("world-2026.11/sneaky.py", b"print(1)")]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "sneaky.py")


def test_missing_listed_file(data_dir, release):
    files = {"a.bin": b"real"}
    listed = {"a.bin": {"sha256": sha256(b"real"), "size": 4}, "b.bin": {"sha256": sha256(b""), "size": 0}}
    release.add("world", "2026.11", files=files, listed=listed)
    assert_refused(data_dir, release, "b.bin")


def test_missing_pack_json(data_dir, release):
    release.add("world", "2026.11", [dir_entry("world-2026.11"), file_entry("world-2026.11/a.bin", b"x")])
    assert_refused(data_dir, release, "pack.json")


def test_pack_json_listing_an_unsafe_path(data_dir, release):
    listed = {"../../outside": {"sha256": sha256(b""), "size": 0}}
    release.add("world", "2026.11", files={}, listed=listed)
    assert_refused(data_dir, release, "outside")


@pytest.mark.parametrize(
    "evil",
    [
        "../evil",
        "world-2026.11/../../evil",
        "world-2026.11/a/../../../evil",
        "/{tmp}/abs-evil",
        "C:/evil",
        "world-2026.11\\..\\..\\evil",
    ],
)
def test_path_tricks_are_refused_before_anything_is_written(data_dir, release, tmp_path, evil):
    evil = evil.format(tmp=str(tmp_path).strip("/"))
    entries = [*pack_entries("world", "2026.11"), file_entry(evil, b"pwned")]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "unsafe|outside")
    assert not list(tmp_path.rglob("*evil*"))


def test_member_outside_the_pack_directory(data_dir, release):
    entries = [*pack_entries("world", "2026.11"), file_entry("other-dir/file", b"x")]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "outside")


@pytest.mark.parametrize(
    ("kind", "target", "reason"),
    [
        (tarfile.SYMTYPE, "/etc/passwd", "is a link"),
        (tarfile.SYMTYPE, "pack.json", "is a link"),
        (tarfile.LNKTYPE, "world-2026.11/pack.json", "is a link"),
        (tarfile.CHRTYPE, "", "is a device or special"),
        (tarfile.BLKTYPE, "", "is a device or special"),
        (tarfile.FIFOTYPE, "", "is a device or special"),
    ],
)
def test_links_and_special_files_are_refused(data_dir, release, kind, target, reason):
    entries = [*pack_entries("world", "2026.11"), special_entry("world-2026.11/link", kind, target)]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, f"'world-2026.11/link' {reason}")


def test_duplicate_members_are_refused(data_dir, release):
    entries = [*pack_entries("world", "2026.11"), file_entry("world-2026.11/countries/layer.json", b"again")]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "duplicate")


def test_archive_that_is_not_a_tar_xz(data_dir, release):
    release.add("world", "2026.11")
    junk = b"this is not xz"
    (release.root / "world-2026.11.tar.xz").write_bytes(junk)
    release.packs["world"].update(sha256=sha256(junk), size_bytes=len(junk))
    release.write()
    assert_refused(data_dir, release, "archive")


def test_index_schema_2_is_refused_before_downloading(data_dir, release):
    release.add("world", "2026.11", schema=2)
    (release.root / "world-2026.11.tar.xz").unlink()
    assert_refused(data_dir, release, "schema 2", exc=UnsupportedSchemaError)


def test_pack_json_schema_2_is_refused(data_dir, release):
    release.add("world", "2026.11", schema=1, entries=pack_entries("world", "2026.11", schema=2))
    assert_refused(data_dir, release, "schema", exc=StoreError)


@pytest.mark.parametrize(("name", "version"), [("ca", "2026.11"), ("world", "2026.10")])
def test_pack_json_must_match_the_index_entry(data_dir, release, name, version):
    manifest = pack_json(name, version, {})
    entries = [dir_entry("world-2026.11"), file_entry("world-2026.11/pack.json", manifest)]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "index")


def test_download_larger_than_the_index_says_is_cut_off(data_dir, release):
    blob = os.urandom(store_constants.DOWNLOAD_SLACK_BYTES * 2)  # random, so xz can't shrink it
    release.add("world", "2026.11", files={"blob.bin": blob}, size=1000)
    assert_refused(data_dir, release, "larger|size", exc=DownloadError)


# -- versions, pin, update, prune, remove ---------------------------------------------------------


def install_versions(data_dir, release, *versions, **settings):
    store = None
    for v in versions:
        release.add("world", v)
        store = make_store(data_dir, release, **settings)
        store.install("world")
    return store


def test_current_is_the_newest_installed(data_dir, release):
    store = install_versions(data_dir, release, "2026.10", "2026.10.2", "2026.10.10")
    # numeric order, not string order
    assert store.installed() == {"world": ["2026.10", "2026.10.2", "2026.10.10"]}
    assert store.current("world").name == "world-2026.10.10"


def test_pin_holds_a_version(data_dir, release):
    install_versions(data_dir, release, "2026.10", "2026.11")
    assert make_store(data_dir, release, pin="2026.10").current("world").name == "world-2026.10"
    with pytest.raises(PackNotInstalled) as err:
        make_store(data_dir, release, pin="2026.09").current("world")
    assert "world" in str(err.value) and "placewise data install world --version 2026.09" in str(err.value)


def test_not_installed_names_the_install_command(data_dir, release):
    with pytest.raises(PackNotInstalled) as err:
        make_store(data_dir, release).current("world")
    assert "placewise data install world" in str(err.value)
    assert err.value.name == "world"


def test_ensure_with_a_pin_installs_only_the_pinned_version(data_dir, release):
    release.add("world", "2026.11")
    assert make_store(data_dir, release, pin="2026.11").ensure("world").name == "world-2026.11"
    other = data_dir / "other"
    with pytest.raises(StoreError, match=r"2026\.10"):
        make_store(other, release, pin="2026.10").ensure("world")
    assert make_store(other, release).installed() == {}


def test_update_installs_newer_versions_and_never_deletes(data_dir, release):
    store = install_versions(data_dir, release, "2026.10")
    assert store.update() == []
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    assert store.update() == [("world", "2026.10", "2026.11")]
    assert store.installed() == {"world": ["2026.10", "2026.11"]}
    assert store.update() == []


def test_update_named_pack_installs_it_and_ignores_older_index(data_dir, release):
    release.add("ca", "2026.10")
    store = install_versions(data_dir, release, "2026.11")
    assert store.update(["ca"]) == [("ca", None, "2026.10")]
    release.add("world", "2026.10")  # index rolled back: nothing to do
    assert make_store(data_dir, release).update() == []


def test_update_leaves_pinned_packs_alone(data_dir, release):
    install_versions(data_dir, release, "2026.10")
    release.add("world", "2026.11")
    store = make_store(data_dir, release, pin="2026.10")
    assert store.update() == []
    assert store.installed() == {"world": ["2026.10"]}


def test_update_offline_is_an_error(data_dir, release):
    install_versions(data_dir, release, "2026.10")
    with pytest.raises(OfflineError):
        make_store(data_dir, release, offline=True).update()


def test_prune_keeps_newest_current_and_pinned(data_dir, release):
    install_versions(data_dir, release, "2026.08", "2026.09", "2026.10", "2026.11")
    pinned = make_store(data_dir, release, pin="2026.08")
    assert pinned.prune(keep=1) == [("world", "2026.09"), ("world", "2026.10")]
    assert pinned.installed() == {"world": ["2026.08", "2026.11"]}
    store = make_store(data_dir, release)
    assert store.prune(keep=2) == []
    assert store.prune() == [("world", "2026.08")]
    assert store.installed() == {"world": ["2026.11"]}
    with pytest.raises(ValueError):
        store.prune(keep=0)


def test_prune_never_follows_links_or_touches_strangers(data_dir, release, tmp_path):
    install_versions(data_dir, release, "2026.10", "2026.11")
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "precious.txt").write_text("keep me")
    (data_dir / "packs" / "world-2026.01").symlink_to(victim, target_is_directory=True)
    (data_dir / "packs" / "not-a-pack").mkdir()
    (data_dir / "precious.txt").write_text("keep me too")
    store = make_store(data_dir, release)
    removed = store.prune()
    assert ("world", "2026.10") in removed
    assert (victim / "precious.txt").exists()
    assert (data_dir / "packs" / "not-a-pack").is_dir()
    assert (data_dir / "precious.txt").exists()


def test_remove_one_version_or_all(data_dir, release):
    store = install_versions(data_dir, release, "2026.10", "2026.11")
    assert store.remove("world", "2026.10") == ["2026.10"]
    assert store.installed() == {"world": ["2026.11"]}
    with pytest.raises(PackNotInstalled):
        store.remove("world", "2026.10")
    assert store.remove("world") == ["2026.11"]
    assert store.installed() == {}
    with pytest.raises(PackNotInstalled):
        store.remove("world")
    with pytest.raises(ValueError):
        store.remove("../packs")


# -- verify ---------------------------------------------------------------------------------------


def test_verify_reports_tampering_and_extra_files(data_dir, release):
    release.add("ca", "2026.11")
    store = install_versions(data_dir, release, "2026.11")
    store.install("ca")
    assert store.verify() == [] and store.verify("world") == []
    world = store.current("world")
    (world / "countries" / "layer.json").write_text("tampered")
    (world / "extra.txt").write_text("hi")
    problems = store.verify()
    assert len(problems) == 2
    assert all(p.startswith("world-2026.11") for p in problems)
    assert any("countries/layer.json" in p for p in problems) and any("extra.txt" in p for p in problems)
    assert store.verify("ca") == []
    with pytest.raises(PackNotInstalled):
        store.verify("nowhere")


# -- locking --------------------------------------------------------------------------------------


def test_a_held_lock_blocks_install_until_timeout(data_dir, release, monkeypatch):
    release.add("world", "2026.11")
    monkeypatch.setattr(store_constants, "LOCK_WAIT_S", 0.3)
    store = make_store(data_dir, release)
    data_dir.mkdir(parents=True)
    lock = store.layout.lock
    lock.write_text("12345")
    with pytest.raises(LockError, match=re.escape(str(lock))):
        store.install("world")
    assert store.installed() == {}
    assert lock.exists()  # someone else's lock is not ours to delete


def test_a_stale_lock_is_broken(data_dir, release):
    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    data_dir.mkdir(parents=True)
    store.layout.lock.write_text("12345")
    old = time.time() - store_constants.LOCK_STALE_S - 10
    os.utime(store.layout.lock, (old, old))
    assert store.install("world").is_dir()
    assert not store.layout.lock.exists()


def test_concurrent_installs_do_not_collide(data_dir, release):
    release.add("world", "2026.11")
    results, errors = [], []

    def worker():
        try:
            results.append(make_store(data_dir, release).install("world"))
        except Exception as e:  # pragma: no cover - surfaced by the assert below
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert len(set(results)) == 1
    assert make_store(data_dir, release).verify() == []
    assert leftovers(data_dir) == []


# -- HTTP -----------------------------------------------------------------------------------------


def test_install_over_http_with_mirror_fallback_and_generic_user_agent(data_dir, tmp_path):
    served = tmp_path / "served"
    Release(served / "release").add("world", "2026.11")
    with LocalServer(served) as server:
        store = Store(
            data_dir,
            DataSettings(mirrors=(server.url + "missing/index.json", server.url + "release/")),
            index_url=server.url + "also-missing/index.json",
        )
        assert store.install("world").name == "world-2026.11"
        assert set(server.user_agents) == {f"placewise/{placewise.__version__}"}
    cached = json.loads((data_dir / "index.json").read_text())
    assert cached["packs"]["world"]["url"] == server.url + "release/world-2026.11.tar.xz"


def test_http_download_size_limit(data_dir, tmp_path):
    served = tmp_path / "served"
    blob = os.urandom(store_constants.DOWNLOAD_SLACK_BYTES * 2)
    Release(served).add("world", "2026.11", files={"blob.bin": blob}, size=1000)
    with LocalServer(served) as server:
        store = Store(data_dir, index_url=server.url + "index.json")
        with pytest.raises(DownloadError, match=r"larger|size"):
            store.install("world")
    assert store.installed() == {}
    assert leftovers(data_dir) == []
