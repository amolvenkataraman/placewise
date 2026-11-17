"""placewise.store.install: install, ensure and update, and the integrity checks an install runs.
No network: packs are served from file:// URLs."""

import json
import os
import tarfile

import pytest
from store_kit import (
    dir_entry,
    file_entry,
    install_versions,
    leftovers,
    make_store,
    pack_entries,
    pack_json,
    sha256,
    special_entry,
)

from placewise.constants import store as store_constants
from placewise.store import DownloadError, IntegrityError, OfflineError, StoreError, UnsupportedSchemaError


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
    release.add("can", "2026.10")
    store = install_versions(data_dir, release, "2026.11")
    assert store.update(["can"]) == [("can", None, "2026.10")]
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


@pytest.mark.parametrize(("name", "version"), [("can", "2026.11"), ("world", "2026.10")])
def test_pack_json_must_match_the_index_entry(data_dir, release, name, version):
    manifest = pack_json(name, version, {})
    entries = [dir_entry("world-2026.11"), file_entry("world-2026.11/pack.json", manifest)]
    release.add("world", "2026.11", entries)
    assert_refused(data_dir, release, "index")


def test_download_larger_than_the_index_says_is_cut_off(data_dir, release):
    blob = os.urandom(store_constants.DOWNLOAD_SLACK_BYTES * 2)  # random, so xz can't shrink it
    release.add("world", "2026.11", files={"blob.bin": blob}, size=1000)
    assert_refused(data_dir, release, "larger|size", exc=DownloadError)
