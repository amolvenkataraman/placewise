"""placewise.config.loader: defaults < file < env < keyword overrides, discovery, unknown keys and origins."""

import importlib.util
from pathlib import Path

import pytest
from config_kit import write_json

from placewise.config import (
    ConfigError,
    config_dir,
    explain_settings,
    find_config,
    load_settings,
)
from placewise.model import Settings

HAS_TOML = any(importlib.util.find_spec(name) for name in ("tomllib", "tomli"))
needs_toml = pytest.mark.skipif(not HAS_TOML, reason="needs tomllib (3.11+) or tomli")

# --- defaults and precedence -----------------------------------------------------------------


def test_no_file_no_env_gives_shipped_defaults(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path / "nowhere")}
    assert load_settings(env=env) == Settings()
    assert load_settings(path=False, env={}) == Settings()


def test_file_beats_defaults_env_beats_file_kwargs_beat_env(tmp_path):
    cfg = write_json(
        tmp_path / "placewise.json", {"near": {"airport": 5, "lake": 2}, "data": {"offline": True}}
    )
    s = load_settings(cfg, env={})
    assert s.near.airport == 5 and s.near.lake == 2 and s.data.offline
    assert s.near.park_tier1 == 25  # untouched default survives

    env = {"PLACEWISE_NEAR_AIRPORT": "7.5"}
    s = load_settings(cfg, env=env)
    assert s.near.airport == 7.5 and s.near.lake == 2

    s = load_settings(cfg, env=env, near_airport=9)
    assert s.near.airport == 9
    s = load_settings(cfg, env=env, near={"airport": 11})  # section dicts work too
    assert s.near.airport == 11 and s.near.lake == 2


@needs_toml
def test_toml_config_file(tmp_path):
    cfg = tmp_path / "placewise.toml"
    cfg.write_text('[worldview]\norder = ["IN", "de_facto"]\n\n[server]\nport = 9000\n')
    s = load_settings(cfg, env={})
    assert s.worldview.order == ("IN", "de_facto") and s.server.port == 9000


# --- discovery --------------------------------------------------------------------------------


def test_discovery_order(tmp_path, monkeypatch):
    explicit = write_json(tmp_path / "explicit.json", {"server": {"port": 1001}})
    via_env = write_json(tmp_path / "via_env.json", {"server": {"port": 1002}})
    xdg = tmp_path / "xdg"
    (xdg / "placewise").mkdir(parents=True)
    in_config_dir = write_json(xdg / "placewise" / "placewise.json", {"server": {"port": 1004}})
    in_cwd = write_json(Path.cwd() / "placewise.json", {"server": {"port": 1003}})

    env = {"PLACEWISE_CONFIG": str(via_env), "XDG_CONFIG_HOME": str(xdg)}
    assert find_config(explicit, env) == explicit
    assert find_config(None, env) == via_env
    del env["PLACEWISE_CONFIG"]
    assert find_config(None, env) == in_cwd
    in_cwd.unlink()
    assert find_config(None, env) == in_config_dir
    assert load_settings(env=env).server.port == 1004
    assert find_config(False, env) is None


def test_toml_preferred_over_json_in_one_place(tmp_path):
    xdg = tmp_path / "xdg"
    (xdg / "placewise").mkdir(parents=True)
    write_json(xdg / "placewise" / "placewise.json", {})
    (xdg / "placewise" / "placewise.toml").write_text("")
    assert find_config(None, {"XDG_CONFIG_HOME": str(xdg)}).name == "placewise.toml"


def test_named_files_must_exist(tmp_path):
    with pytest.raises(ConfigError, match=r"missing\.toml"):
        load_settings(tmp_path / "missing.toml", env={})
    with pytest.raises(ConfigError, match="PLACEWISE_CONFIG"):
        load_settings(env={"PLACEWISE_CONFIG": str(tmp_path / "gone.toml")})


def test_config_dir_per_platform(tmp_path):
    home = Path.home()
    assert config_dir({"XDG_CONFIG_HOME": str(tmp_path)}, "linux") == tmp_path / "placewise"
    assert config_dir({}, "linux") == home / ".config" / "placewise"
    assert config_dir({"XDG_CONFIG_HOME": "relative/path"}, "linux") == home / ".config" / "placewise"
    assert config_dir({}, "darwin") == home / "Library" / "Application Support" / "placewise"
    assert config_dir({"APPDATA": str(tmp_path)}, "win32") == tmp_path / "placewise"


# --- unknown keys -----------------------------------------------------------------------------


def test_unknown_keys_are_errors_naming_key_and_file(tmp_path):
    cfg = write_json(tmp_path / "typo.json", {"near": {"airprot": 5}})
    with pytest.raises(ConfigError, match=r"near\.airprot.*typo\.json|typo\.json.*near\.airprot"):
        load_settings(cfg, env={})
    cfg = write_json(tmp_path / "section.json", {"neer": {"airport": 5}})
    with pytest.raises(ConfigError, match=r"neer.*section\.json|section\.json.*neer"):
        load_settings(cfg, env={})
    cfg = write_json(tmp_path / "flat.json", {"near": 5})
    with pytest.raises(ConfigError, match=r"flat\.json"):
        load_settings(cfg, env={})


def test_bad_values_in_the_file_name_the_file(tmp_path):
    cfg = write_json(tmp_path / "bad.json", {"names": {"prefer": "posh"}})
    with pytest.raises(ConfigError, match=r"bad\.json.*names\.prefer|names\.prefer.*bad\.json"):
        load_settings(cfg, env={})


# --- explain ----------------------------------------------------------------------------------


def test_explain_settings_reports_each_values_origin(tmp_path):
    cfg = write_json(tmp_path / "placewise.json", {"near": {"airport": 5, "lake": 2}})
    env = {"PLACEWISE_NEAR_LAKE": "3", "PLACEWISE_DATA_OFFLINE": "true"}
    report = explain_settings(cfg, env=env, server_port=9100)
    assert report["near.airport"] == (5.0, f"file:{cfg}")
    assert report["near.lake"] == (3.0, "env:PLACEWISE_NEAR_LAKE")
    assert report["data.offline"] == (True, "env:PLACEWISE_DATA_OFFLINE")
    assert report["server.port"] == (9100, "kwarg:server_port")
    assert report["near.park_tier1"] == (25.0, "default")
    assert report["worldview.order"] == (("de_facto",), "default")
    # every field of every section is listed
    assert len(report) == sum(
        len(getattr(Settings(), s).__dataclass_fields__) for s in Settings.__dataclass_fields__
    )
