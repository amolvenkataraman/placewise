"""placewise.store.maintenance: verify, prune and remove.
No network: packs are served from file:// URLs."""

import pytest
from store_kit import install_versions, make_store

from placewise.store import PackNotInstalled


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


def test_verify_reports_tampering_and_extra_files(data_dir, release):
    release.add("can", "2026.11")
    store = install_versions(data_dir, release, "2026.11")
    store.install("can")
    assert store.verify() == [] and store.verify("world") == []
    world = store.current("world")
    (world / "countries" / "layer.json").write_text("tampered")
    (world / "extra.txt").write_text("hi")
    problems = store.verify()
    assert len(problems) == 2
    assert all(p.startswith("world-2026.11") for p in problems)
    assert any("countries/layer.json" in p for p in problems) and any("extra.txt" in p for p in problems)
    assert store.verify("can") == []
    with pytest.raises(PackNotInstalled):
        store.verify("nowhere")


def test_size_on_disk_is_the_installed_files_not_the_archive(data_dir, release):
    from store_kit import DEFAULT_FILES, make_store

    release.add("world", "2026.11")
    store = make_store(data_dir, release)
    path = store.install("world")
    expected = sum(len(v) for v in DEFAULT_FILES.values()) + (path / "pack.json").stat().st_size
    assert store.size_on_disk("world", "2026.11") == expected
