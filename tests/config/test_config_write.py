"""placewise.config.write: `placewise data mode` changes one key of placewise.toml (or .json) in
place, keeping the rest of the file as the user wrote it."""

import json

import pytest

from placewise.config import ConfigError, load_settings, set_setting, user_config_path


def test_creates_the_file_and_section(tmp_path):
    path = tmp_path / "conf" / "placewise.toml"
    set_setting(path, "data", "mode", "locked")
    assert load_settings(path=path, env={}).data.mode == "locked"


def test_replaces_the_key_and_keeps_comments_and_other_sections(tmp_path):
    path = tmp_path / "placewise.toml"
    path.write_text(
        '# my settings\n[near]\nairport = 5\n\n[data]\n# how packs arrive\nmode = "auto"  # default\n'
        'pin = "2026.11"\n\n[label]\nstyle = "city"\n'
    )
    set_setting(path, "data", "mode", "manual")
    text = path.read_text()
    assert "# my settings" in text and "# how packs arrive" in text
    assert text.count("mode =") == 1
    s = load_settings(path=path, env={})
    assert s.data.mode == "manual" and s.data.pin == "2026.11"
    assert s.near.airport == 5 and s.label.style == "city"


def test_adds_a_key_to_an_existing_section_and_writes_lists(tmp_path):
    path = tmp_path / "placewise.toml"
    path.write_text('[data]\npin = "2026.11"\n[server]\nport = 9000\n')
    set_setting(path, "data", "auto_packs", ("country", "parks"))
    s = load_settings(path=path, env={})
    assert s.data.auto_packs == ("country", "parks") and s.server.port == 9000


def test_json_files_are_edited_as_json(tmp_path):
    path = tmp_path / "placewise.json"
    path.write_text(json.dumps({"near": {"airport": 5}}))
    set_setting(path, "data", "mode", "locked")
    assert json.loads(path.read_text()) == {"near": {"airport": 5}, "data": {"mode": "locked"}}


def test_values_are_validated_before_anything_is_written(tmp_path):
    path = tmp_path / "placewise.toml"
    path.write_text('[data]\nmode = "auto"\n')
    with pytest.raises(ConfigError):
        set_setting(path, "data", "mode", "sometimes")
    with pytest.raises(ConfigError):
        set_setting(path, "data", "nope", "x")
    assert path.read_text() == '[data]\nmode = "auto"\n'


def test_user_config_path_is_the_file_in_use_or_the_per_user_one(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.delenv("PLACEWISE_CONFIG", raising=False)
    assert user_config_path() == tmp_path / "xdg" / "placewise" / "placewise.toml"
    local = tmp_path / "cwd" / "placewise.toml"  # the conftest's cwd
    local.write_text("")
    assert user_config_path() == local
