"""`placewise data ...` through main(argv), checking output and exit codes."""

import pytest

from placewise.cli import main


@pytest.fixture
def run(capsys, data_dir, release):
    """Run the CLI against the test data dir and release; returns (exit code, stdout, stderr)."""

    def _run(*argv, index=True):
        base = ["--data-dir", str(data_dir)]
        if index:
            base += ["--index-url", release.index_url]
        code = main([*base, *argv])
        out, err = capsys.readouterr()
        return code, out, err

    return _run


def test_where_prints_the_data_dir(run, data_dir):
    code, out, err = run("data", "where")
    assert (code, out.strip(), err) == (0, str(data_dir), "")


def test_where_uses_env_without_options(capsys, tmp_path, monkeypatch):
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "from-env"))
    assert main(["data", "where"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "from-env")


def test_install_list_update_prune_remove(run, release):
    release.add("world", "2026.10")
    release.add("ca", "2026.11")
    code, out, _ = run("data", "install", "world", "ca")
    assert code == 0 and "world 2026.10" in out and "ca 2026.11" in out

    code, out, _ = run("data", "install", "world")
    assert code == 0 and "already installed" in out

    release.add("world", "2026.11")
    code, out, _ = run("data", "list")
    assert code == 0
    lines = {tuple(line.split()[:2]): line for line in out.splitlines() if line.strip()}
    assert "current" in lines[("world", "2026.10")]
    assert "available" in lines[("world", "2026.11")]
    assert "current" in lines[("ca", "2026.11")]

    code, out, _ = run("data", "update")
    assert code == 0 and "world 2026.10 -> 2026.11" in out
    code, out, _ = run("data", "update")
    assert code == 0 and "up to date" in out

    code, out, _ = run("data", "verify")
    assert code == 0 and "ok" in out

    code, out, _ = run("data", "prune", "--keep", "1")
    assert code == 0 and "world 2026.10" in out

    code, out, _ = run("data", "remove", "ca")
    assert code == 0 and "ca 2026.11" in out
    code, out, _ = run("data", "list", "--offline")
    assert "ca" in out  # still in the cached index, as available
    assert "installed" not in next(line for line in out.splitlines() if line.startswith("ca"))


def test_list_marks_pinned(run, release, data_dir, capsys):
    release.add("world", "2026.10")
    run("data", "install", "world")
    release.add("world", "2026.11")
    run("data", "install", "world")
    # the pin comes from settings; the CLI has no config loader yet, so go through the library
    from placewise.cli import _list
    from placewise.model import DataSettings
    from placewise.store import Store

    _list(Store(data_dir, DataSettings(pin="2026.10"), index_url=release.index_url))
    out = capsys.readouterr().out
    pinned = next(line for line in out.splitlines() if "2026.10" in line)
    assert "pinned" in pinned and "current" in pinned
    assert "current" not in next(line for line in out.splitlines() if "2026.11" in line)


def test_install_with_version(run, release):
    release.add("world", "2026.11")
    assert run("data", "install", "world", "--version", "2026.11")[0] == 0
    code, _, err = run("data", "install", "world", "--version", "2025.01")
    assert code == 1 and "2025.01" in err


def test_errors_are_one_line_with_exit_1(run, release):
    release.add("world", "2026.11", sha="0" * 64)
    code, _, err = run("data", "install", "world")
    assert code == 1
    assert err.startswith("placewise: error:") and err.count("\n") == 1
    assert "Traceback" not in err


def test_offline_without_cache(run):
    code, _, err = run("--offline", "data", "install", "world")
    assert code == 1 and "offline" in err and err.count("\n") == 1


def test_global_options_work_after_the_subcommand(capsys, data_dir):
    assert main(["data", "where", "--data-dir", str(data_dir)]) == 0
    assert capsys.readouterr().out.strip() == str(data_dir)


def test_list_with_no_index_still_shows_installed(run, release, data_dir):
    release.add("world", "2026.11")
    run("data", "install", "world")
    (data_dir / "index.json").unlink()
    (release.root / "index.json").unlink()
    code, out, err = run("data", "list")
    assert code == 0
    assert "world" in out and "2026.11" in out and "current" in out
    assert "index" in err  # a warning, not a failure


def test_verify_reports_problems_with_exit_1(run, release, data_dir):
    release.add("world", "2026.11")
    run("data", "install", "world")
    (data_dir / "packs" / "world-2026.11" / "pack.json").write_text("{}")
    code, out, err = run("data", "verify")
    assert code == 1 and "world-2026.11" in out + err


def test_verify_unknown_pack(run):
    code, _, err = run("data", "verify", "nowhere")
    assert code == 1 and "nowhere" in err


def test_remove_missing_is_an_error(run):
    code, _, err = run("data", "remove", "world")
    assert code == 1 and "world" in err


@pytest.mark.parametrize(
    "argv",
    [[], ["data"], ["data", "bogus"], ["data", "install"], ["data", "prune", "--keep", "x"], ["--nope"]],
)
def test_usage_errors_exit_2(capsys, argv):
    assert main(argv) == 2
    assert capsys.readouterr().err


def test_help_exits_0(capsys):
    assert main(["--help"]) == 0
    assert "data" in capsys.readouterr().out
