"""Release tooling: archives, index.json, ATTRIBUTION.md and SHA256SUMS from built packs, and the
`gh release create` command. Synthetic packs only; nothing touches the network or runs gh."""

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from packbuild import release
from placewise.packs import LayerData, PackIntegrityError, open_pack, write_pack
from placewise.store import Store

CREATED = "2026-11-17T00:00:00Z"


def _pack(out, name, version="2026.11", sources=("naturalearth",)):
    layer = LayerData(
        name="spots",
        kind="point",
        columns={"id": [f"synthetic:{name}:0", f"synthetic:{name}:1"], "name": ["Spot A", "Spot B"]},
        sources=tuple(sources),
        lat=np.array([10.0, -20.5]),
        lon=np.array([30.25, -40.0]),
    )
    return write_pack(out, name, version, [layer], created=CREATED)


@pytest.fixture
def built(tmp_path):
    out = tmp_path / "built"
    world = _pack(out, "world", sources=("naturalearth", "geonames"))
    return [world, _pack(out, "usa", sources=("uscensus",))]


@pytest.fixture(autouse=True)
def _no_publish_env(monkeypatch):
    monkeypatch.delenv(release.ALLOW_PUBLISH_ENV, raising=False)


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# --- prepare_release ---------------------------------------------------------------------------


def test_prepare_writes_archives_index_attribution_and_sums(tmp_path, built):
    out = tmp_path / "release"
    plan = release.prepare_release(built, out)
    names = {p.name for p in out.iterdir()}
    assets = {"index.json", "ATTRIBUTION.md", "SHA256SUMS", "world-2026.11.tar.xz", "usa-2026.11.tar.xz"}
    assert assets <= names
    assert [p.name for p in plan.packs] == ["world", "usa"]
    assert plan.version == "2026.11"
    assert [a.name for a in plan.archives] == ["world-2026.11.tar.xz", "usa-2026.11.tar.xz"]
    assert all(a.parent == out for a in plan.archives)
    assert plan.assets == (plan.index, plan.attribution, plan.sums, *plan.archives)
    assert plan.notes.is_file() and plan.notes not in plan.assets


def test_index_lists_each_pack_with_a_relative_url_and_the_archive_hash(tmp_path, built):
    plan = release.prepare_release(built, tmp_path / "release")
    doc = json.loads(plan.index.read_text())
    assert doc["schema"] == 1 and set(doc["packs"]) == {"world", "usa"}
    world = doc["packs"]["world"]
    assert world["url"] == "world-2026.11.tar.xz"  # relative: a mirror is a copy of the directory
    assert world["sha256"] == _sha(tmp_path / "release" / "world-2026.11.tar.xz")
    assert world["size_bytes"] == (tmp_path / "release" / "world-2026.11.tar.xz").stat().st_size
    assert world["sources"] == ["naturalearth", "geonames"] and world["version"] == "2026.11"


def test_sha256sums_covers_every_asset_in_sha256sum_format(tmp_path, built):
    plan = release.prepare_release(built, tmp_path / "release")
    lines = plan.sums.read_text().splitlines()
    listed = {line.split("  ", 1)[1]: line.split("  ", 1)[0] for line in lines}
    expected = {p.name for p in plan.assets if p != plan.sums}
    assert set(listed) == expected
    for name, digest in listed.items():
        assert digest == _sha(tmp_path / "release" / name)
    assert lines == sorted(lines, key=lambda line: line.split("  ", 1)[1])


def test_attribution_covers_only_the_sources_the_packs_use(tmp_path, built):
    plan = release.prepare_release(built[1:], tmp_path / "release")  # the usa pack alone
    text = plan.attribution.read_text()
    assert "## US Census Bureau" in text
    assert "Natural Earth" not in text and "GeoNames" not in text and "Statistics Canada" not in text
    assert "| boundaries | usa |" in text and "| boundaries | world |" not in text


def test_a_release_is_reproducible(tmp_path, built):
    a = release.prepare_release(built, tmp_path / "a")
    b = release.prepare_release(built, tmp_path / "b")
    for x, y in zip((*a.assets, a.notes), (*b.assets, b.notes), strict=True):
        assert x.name == y.name and x.read_bytes() == y.read_bytes()


def test_the_built_packs_are_left_in_place(tmp_path, built):
    before = {p: _sha(p / "pack.json") for p in built}
    release.prepare_release(built, tmp_path / "release")
    assert {p: _sha(p / "pack.json") for p in built} == before
    for p in built:
        open_pack(p, verify=True)


def test_the_store_installs_from_the_prepared_directory(tmp_path, built):
    plan = release.prepare_release(built, tmp_path / "release")
    store = Store(data_dir=tmp_path / "data", index_url=plan.index.as_uri())
    for name in ("world", "usa"):
        pack = open_pack(store.install(name), verify=True)
        assert pack.name == name and pack["spots"].value("name", 1) == "Spot B"
    assert store.verify() == []


def test_refuses_two_packs_with_one_name(tmp_path):
    a = _pack(tmp_path / "a", "world", "2026.10")
    b = _pack(tmp_path / "b", "world", "2026.11")
    with pytest.raises(ValueError, match="more than once: world"):
        release.prepare_release([a, b], tmp_path / "release")


def test_refuses_a_pack_of_another_schema(tmp_path, built):
    manifest = built[1] / "pack.json"
    doc = json.loads(manifest.read_text())
    manifest.write_text(json.dumps({**doc, "schema": 2}))
    with pytest.raises(ValueError, match=r"us.*schema 2"):
        release.prepare_release(built, tmp_path / "release")
    assert not (tmp_path / "release" / "index.json").exists()


def test_refuses_sources_missing_from_the_registry(tmp_path):
    odd = _pack(tmp_path / "built", "odd", sources=("naturalearth", "not-a-registered-source"))
    with pytest.raises(ValueError, match="not-a-registered-source"):
        release.prepare_release([odd], tmp_path / "release")


def test_refuses_a_damaged_pack(tmp_path, built):
    column = built[0] / "spots" / "col" / "name.npy"
    data = column.read_bytes()
    column.write_bytes(data[:-1] + bytes([data[-1] ^ 0xFF]))
    with pytest.raises(PackIntegrityError):
        release.prepare_release(built, tmp_path / "release")


def test_refuses_a_directory_not_named_after_its_pack(tmp_path, built):
    moved = built[0].rename(built[0].with_name("world-latest"))
    with pytest.raises(ValueError, match=r"world-2026\.11"):
        release.prepare_release([moved], tmp_path / "release")


def test_refuses_nothing_to_release(tmp_path):
    with pytest.raises(ValueError, match="no packs"):
        release.prepare_release([], tmp_path / "release")


def test_the_default_tag_is_the_newest_pack_version(tmp_path):
    out = tmp_path / "built"
    packs = [_pack(out, "world", "2026.11"), _pack(out, "usa", "2026.11.1")]
    plan = release.prepare_release(packs, tmp_path / "r")
    assert plan.version == "2026.11.1"


# --- publish -----------------------------------------------------------------------------------


@pytest.fixture
def plan(tmp_path, built):
    return release.prepare_release(built, tmp_path / "release")


@pytest.fixture
def runs(monkeypatch):
    calls = []
    monkeypatch.setattr(release.subprocess, "run", lambda *a, **kw: calls.append((a, kw)))
    return calls


def test_publish_builds_the_gh_command_and_by_default_runs_nothing(plan, runs, capsys):
    cmd = release.publish(plan)
    assert cmd == [
        "gh",
        "release",
        "create",
        "2026.11",
        "--repo",
        "amolvenkataraman/placewise-data",
        "--title",
        "placewise data 2026.11",
        "--notes-file",
        str(plan.notes),
        "--latest",
        *[str(p) for p in plan.assets],
    ]
    assert runs == []
    assert "gh release create 2026.11" in capsys.readouterr().out


def test_publish_takes_the_repo_and_tag_as_arguments(plan, runs):
    cmd = release.publish(plan, repo="someone/mirror", tag="2026.11.2")
    assert cmd[3:6] == ["2026.11.2", "--repo", "someone/mirror"]
    assert runs == []


def test_publish_rejects_odd_tags_and_repos(plan, runs):
    with pytest.raises(ValueError, match="tag"):
        release.publish(plan, tag="latest")
    with pytest.raises(ValueError, match="repo"):
        release.publish(plan, repo="https://example.org/x")


def test_publish_for_real_needs_the_environment_switch(plan, runs, monkeypatch):
    with pytest.raises(PermissionError, match=release.ALLOW_PUBLISH_ENV):
        release.publish(plan, dry_run=False)
    assert runs == []
    monkeypatch.setenv(release.ALLOW_PUBLISH_ENV, "1")
    cmd = release.publish(plan, dry_run=False)
    assert runs == [((cmd,), {"check": True})]


def test_publish_refuses_a_plan_whose_files_are_gone(plan, runs, monkeypatch):
    plan.archives[0].unlink()
    monkeypatch.setenv(release.ALLOW_PUBLISH_ENV, "1")
    with pytest.raises(FileNotFoundError, match=r"world-2026\.11\.tar\.xz"):
        release.publish(plan, dry_run=False)
    assert runs == []


def test_no_real_subprocess_is_reachable_in_these_tests():
    # guard for the guard: the module calls subprocess.run through its own reference
    assert release.subprocess is subprocess


# --- CLI ---------------------------------------------------------------------------------------


def test_cli_prepares_only_by_default(tmp_path, built, runs, capsys):
    out = tmp_path / "release"
    assert release.main(["--packs", *map(str, built), "--out", str(out)]) == 0
    assert (out / "index.json").is_file() and runs == []
    printed = capsys.readouterr().out
    assert "world-2026.11.tar.xz" in printed and "gh release create" in printed


def test_cli_publish_refuses_without_the_environment_switch(tmp_path, built, runs, capsys):
    out = tmp_path / "release"
    assert release.main(["--packs", *map(str, built), "--out", str(out), "--publish"]) == 2
    assert release.ALLOW_PUBLISH_ENV in capsys.readouterr().err
    assert runs == [] and not out.exists()  # refused before doing any work


def test_cli_publish_with_the_switch_runs_gh_once(tmp_path, built, runs, monkeypatch):
    monkeypatch.setenv(release.ALLOW_PUBLISH_ENV, "1")
    out = tmp_path / "release"
    argv = ["--packs", *map(str, built), "--out", str(out), "--publish", "--tag", "2026.11.1"]
    assert release.main(argv) == 0
    [((cmd,), kw)] = runs
    assert cmd[:4] == ["gh", "release", "create", "2026.11.1"] and kw == {"check": True}
