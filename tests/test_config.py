"""placewise.config: defaults < file < env < keyword overrides, origins and the worldview lock."""

import importlib.util
import json
from pathlib import Path

import pytest

from placewise.config import (
    ConfigError,
    WorldviewLockedError,
    config_dir,
    effective_worldview,
    explain_settings,
    find_config,
    load_settings,
)
from placewise.model import Settings

HAS_TOML = any(importlib.util.find_spec(name) for name in ("tomllib", "tomli"))
needs_toml = pytest.mark.skipif(not HAS_TOML, reason="needs tomllib (3.11+) or tomli")


@pytest.fixture(autouse=True)
def _empty_cwd(tmp_path, monkeypatch):
    """No ./placewise.toml from the developer's checkout leaks into a test."""
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)


def write_json(path, doc):
    path.write_text(json.dumps(doc))
    return path


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


# --- env coercion -----------------------------------------------------------------------------


def test_env_values_are_coerced_from_field_types():
    env = {
        "PLACEWISE_WORLDVIEW_ORDER": "IN, de_facto",
        "PLACEWISE_DATA_OFFLINE": "1",
        "PLACEWISE_SERVER_PORT": "9001",
        "PLACEWISE_SERVER_REQUIRE_KEYS": "no",
        "PLACEWISE_NEAR_PARK_TIER1": "30",
        "PLACEWISE_NEAR_MAX_NEAR": "3",
        "PLACEWISE_DATA_PIN": "2026.11",
        "PLACEWISE_DATA_MIRRORS": "https://a.example/x,https://b.example/y",
        "PLACEWISE_LABEL_TEMPLATE": "",  # empty means unset for optional fields
    }
    s = load_settings(path=False, env=env)
    assert s.worldview.order == ("IN", "de_facto")
    assert s.data.offline is True
    assert s.server.port == 9001 and s.server.require_keys is False
    assert s.near.park_tier1 == 30.0 and s.near.max_near == 3
    assert s.data.pin == "2026.11"
    assert s.data.mirrors == ("https://a.example/x", "https://b.example/y")
    assert s.label.template is None


def test_bad_env_values_name_the_variable():
    with pytest.raises(ConfigError, match="PLACEWISE_SERVER_PORT"):
        load_settings(path=False, env={"PLACEWISE_SERVER_PORT": "eighty"})
    with pytest.raises(ConfigError, match="PLACEWISE_DATA_OFFLINE"):
        load_settings(path=False, env={"PLACEWISE_DATA_OFFLINE": "maybe"})
    with pytest.raises(ConfigError, match="PLACEWISE_SERVER_PORT"):
        load_settings(path=False, env={"PLACEWISE_SERVER_PORT": "70000"})  # model validation


def test_store_env_names_map_onto_data_settings(tmp_path):
    env = {"PLACEWISE_DATA_DIR": str(tmp_path), "PLACEWISE_INDEX_URL": "file:///srv/index.json"}
    s = load_settings(path=False, env=env)
    assert s.data.data_dir == str(tmp_path) and s.data.index_url == "file:///srv/index.json"


def test_unrelated_env_is_ignored():
    assert load_settings(path=False, env={"HOME": "/x", "PATH": "/bin", "PLACEWISE_CONFIG": ""}) == Settings()


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


def test_unknown_env_and_kwargs_are_errors():
    with pytest.raises(ConfigError, match="PLACEWISE_NEAR_AIRPRT"):
        load_settings(path=False, env={"PLACEWISE_NEAR_AIRPRT": "5"})
    with pytest.raises(ConfigError, match="PLACEWISE_WORLDVEIW_ORDER"):
        load_settings(path=False, env={"PLACEWISE_WORLDVEIW_ORDER": "IN"})
    with pytest.raises(ConfigError, match="near_airprot"):
        load_settings(path=False, env={}, near_airprot=5)
    with pytest.raises(ConfigError, match="airprot"):
        load_settings(path=False, env={}, near={"airprot": 5})


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


# --- worldview lock ---------------------------------------------------------------------------


def locked_config(tmp_path):
    return write_json(tmp_path / "locked.json", {"worldview": {"order": ["IN", "de_facto"], "lock": True}})


def test_worldview_lock_refuses_env_order(tmp_path):
    cfg = locked_config(tmp_path)
    with pytest.raises(WorldviewLockedError, match="PLACEWISE_WORLDVIEW_ORDER"):
        load_settings(cfg, env={"PLACEWISE_WORLDVIEW_ORDER": "de_facto"})


def test_worldview_lock_refuses_kwargs_including_unlocking(tmp_path):
    cfg = locked_config(tmp_path)
    with pytest.raises(WorldviewLockedError, match=r"worldview"):
        load_settings(cfg, env={}, worldview_order=("UN",))
    with pytest.raises(WorldviewLockedError):
        load_settings(cfg, env={}, worldview={"order": ["UN"]})
    with pytest.raises(WorldviewLockedError):
        load_settings(cfg, env={}, worldview_lock=False)  # can't unlock from below the operator
    with pytest.raises(WorldviewLockedError):
        load_settings(cfg, env={"PLACEWISE_WORLDVIEW_LOCK": "0"})


def test_worldview_lock_allows_restating_the_same_order_and_other_sections(tmp_path):
    cfg = locked_config(tmp_path)
    s = load_settings(cfg, env={"PLACEWISE_DATA_OFFLINE": "1"}, worldview_order="IN,de_facto")
    assert s.worldview.order == ("IN", "de_facto") and s.worldview.lock and s.data.offline


def test_without_lock_env_and_kwargs_set_the_order(tmp_path):
    s = load_settings(path=False, env={"PLACEWISE_WORLDVIEW_ORDER": "IN,de_facto"})
    assert s.worldview.order == ("IN", "de_facto")
    s = load_settings(path=False, env={}, worldview_order=["UN"])
    assert s.worldview.order == ("UN",)


def test_effective_worldview_ignores_or_rejects_requests_when_locked():
    open_ = Settings()
    assert effective_worldview(open_, ["IN"]) == (("IN",), False)
    assert effective_worldview(open_) == (("de_facto",), False)
    locked = Settings.from_dict({"worldview": {"order": ["IN", "de_facto"], "lock": True}})
    assert effective_worldview(locked, ["UN"]) == (("IN", "de_facto"), True)
    strict = Settings.from_dict({"worldview": {"order": ["IN"], "lock": True, "conflict": "reject"}})
    assert effective_worldview(strict, ["IN"]) == (("IN",), True)
    with pytest.raises(WorldviewLockedError):
        effective_worldview(strict, ["UN"])
