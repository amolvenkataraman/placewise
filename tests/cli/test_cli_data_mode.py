"""`placewise data mode` and `placewise data status`: choosing how packs arrive, and seeing what
is installed, its size on disk, and what auto mode would fetch."""

import pytest

from placewise.cli import main
from placewise.config import load_settings


@pytest.fixture
def run(capsys, data_dir, release):
    def _run(*argv):
        code = main(["--data-dir", str(data_dir), "--index-url", release.index_url, *argv])
        out, err = capsys.readouterr()
        return code, out, err

    return _run


@pytest.fixture
def user_toml(tmp_path):
    return tmp_path / "env-config" / "placewise" / "placewise.toml"  # XDG_CONFIG_HOME from conftest


def test_mode_shows_the_default(run):
    code, out, _ = run("data", "mode")
    assert code == 0
    assert "auto" in out and "default" in out and "country" in out


def test_mode_writes_the_user_config(run, user_toml):
    code, out, _ = run("data", "mode", "manual")
    assert code == 0 and str(user_toml) in out
    assert load_settings(path=user_toml, env={}).data.mode == "manual"
    code, out, _ = run("data", "mode")
    assert "manual" in out and str(user_toml) in out


def test_mode_auto_takes_the_kinds_it_may_fetch(run, user_toml):
    code, _, _ = run("data", "mode", "auto", "--kinds", "country,parks,water")
    assert code == 0
    data = load_settings(path=user_toml, env={}).data
    assert data.mode == "auto" and data.auto_packs == ("country", "parks", "water")


def test_mode_edits_the_config_file_in_use(run, tmp_path):
    local = tmp_path / "placewise.toml"  # ./placewise.toml (the conftest's cwd)
    local.write_text("[near]\nairport = 5\n")
    run("data", "mode", "locked")
    s = load_settings(path=local, env={})
    assert s.data.mode == "locked" and s.near.airport == 5


def test_mode_warns_when_the_environment_overrides_the_file(run, monkeypatch):
    monkeypatch.setenv("PLACEWISE_DATA_MODE", "locked")
    code, _, err = run("data", "mode", "auto")
    assert code == 0 and "PLACEWISE_DATA_MODE" in err


def test_bad_mode_or_kind_is_a_usage_or_one_line_error(run):
    assert run("data", "mode", "sometimes")[0] == 2
    code, _, err = run("data", "mode", "auto", "--kinds", "roads")
    assert code == 1 and "roads" in err and err.count("\n") == 1


def test_locked_refuses_to_install(run, release):
    release.add("world", "2026.11")
    run("data", "mode", "locked")
    code, _, err = run("data", "install", "world")
    assert code == 1 and "locked" in err


def test_status_lists_installed_sizes_and_what_auto_would_fetch(run, release):
    release.add("world", "2026.11")
    release.add("usa", "2026.11")
    release.add("can", "2026.11", meta={"installed_bytes": 110_000_000})
    release.add("can-parks", "2026.11")
    run("data", "install", "world", "usa")
    code, out, _ = run("data", "status")
    assert code == 0
    lines = out.splitlines()
    assert any(line.split()[:1] == ["world"] and "B" in line for line in lines)
    assert any(line.split()[:1] == ["usa"] and "country" in line for line in lines)
    fetch = out[out.index("auto mode fetches") :]
    assert "can " in fetch and "110.0 MB" in fetch and "CA" in fetch
    assert "can-parks" in out[out.index("opt-in") :]  # parks aren't in data.auto_packs


def test_status_in_locked_mode_reads_only_the_cache(run, release, monkeypatch):
    release.add("world", "2026.11")
    run("data", "install", "world")
    from placewise.store import net

    monkeypatch.setattr(net, "_open", lambda url: (_ for _ in ()).throw(AssertionError(url)))
    code, out, _ = run("--offline", "data", "status")
    assert code == 0 and "locked" in out and "world" in out
