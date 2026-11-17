"""Data directory resolution and layout."""

from pathlib import Path

import pytest

from placewise.model import DataSettings
from placewise.store import paths


@pytest.fixture
def bare_env(monkeypatch, tmp_path):
    for var in ("PLACEWISE_DATA_DIR", "XDG_DATA_HOME", "LOCALAPPDATA"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    return tmp_path / "home"


def test_explicit_beats_settings_beats_env(bare_env, monkeypatch, tmp_path):
    monkeypatch.setenv("PLACEWISE_DATA_DIR", str(tmp_path / "env"))
    settings = DataSettings(data_dir=str(tmp_path / "settings"))
    assert paths.resolve_data_dir(tmp_path / "explicit", settings) == tmp_path / "explicit"
    assert paths.resolve_data_dir(None, settings) == tmp_path / "settings"
    assert paths.resolve_data_dir(None, DataSettings()) == tmp_path / "env"
    assert paths.resolve_data_dir() == tmp_path / "env"


def test_user_paths_expand_tilde(bare_env):
    assert paths.resolve_data_dir("~/pw") == bare_env / "pw"
    assert paths.resolve_data_dir(None, DataSettings(data_dir="~/pw2")) == bare_env / "pw2"


@pytest.mark.parametrize("platform", ["linux", "darwin", "win32"])
def test_default_is_dot_placewise_in_home_on_every_platform(bare_env, monkeypatch, tmp_path, platform):
    """Unless configured, every download lives in ~/.placewise/ (one place to find, back up or delete)."""
    monkeypatch.setattr("sys.platform", platform)
    # platform data-dir conventions are ignored on purpose
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.resolve_data_dir() == bare_env / ".placewise"


def test_configured_dir_still_wins_over_the_default(bare_env, tmp_path):
    assert paths.resolve_data_dir(None, DataSettings(data_dir=str(tmp_path / "mine"))) == tmp_path / "mine"


def test_layout(tmp_path):
    layout = paths.Layout(tmp_path)
    assert layout.root == tmp_path
    assert layout.packs == tmp_path / "packs"
    assert layout.pack("world", "2026.11") == tmp_path / "packs" / "world-2026.11"
    assert layout.index == tmp_path / "index.json"
    assert layout.overrides == tmp_path / "overrides.toml"
    assert layout.lock.parent == tmp_path


@pytest.mark.parametrize(
    ("name", "version"),
    [("../x", "2026.11"), ("world", "../../etc"), ("World", "2026.11"), ("", "2026.11"), ("a/b", "2026.11")],
)
def test_layout_refuses_names_that_could_escape(tmp_path, name, version):
    with pytest.raises(ValueError):
        paths.Layout(tmp_path).pack(name, version)


def test_parse_pack_dir_name():
    assert paths.parse_pack_dir("world-2026.11") == ("world", "2026.11")
    assert paths.parse_pack_dir("us-nature-2026.11.2") == ("us-nature", "2026.11.2")
    assert paths.parse_pack_dir(".tmp-abc") is None
    assert paths.parse_pack_dir("world") is None
    assert isinstance(paths.Layout("rel").root, Path)
