"""placewise.config.env: PLACEWISE_<SECTION>_<KEY> variables, coerced from text to each field's type."""

import pytest

from placewise.config import ConfigError, load_settings
from placewise.constants import config as const
from placewise.model import Settings


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


def test_unknown_env_and_kwargs_are_errors():
    with pytest.raises(ConfigError, match="PLACEWISE_NEAR_AIRPRT"):
        load_settings(path=False, env={"PLACEWISE_NEAR_AIRPRT": "5"})
    with pytest.raises(ConfigError, match="PLACEWISE_WORLDVEIW_ORDER"):
        load_settings(path=False, env={"PLACEWISE_WORLDVEIW_ORDER": "IN"})
    with pytest.raises(ConfigError, match="near_airprot"):
        load_settings(path=False, env={}, near_airprot=5)
    with pytest.raises(ConfigError, match="airprot"):
        load_settings(path=False, env={}, near={"airprot": 5})


def test_aliases_carry_the_prefix_from_env_filters_on():
    assert all(name.startswith(const.ENV_PREFIX) for name in const.ENV_ALIASES)


def test_data_mode_and_auto_packs_come_from_the_environment():
    env = {"PLACEWISE_DATA_MODE": "manual", "PLACEWISE_DATA_AUTO_PACKS": "country, parks"}
    s = load_settings(path=False, env=env)
    assert s.data.mode == "manual" and s.data.auto_packs == ("country", "parks")
    with pytest.raises(ConfigError, match="PLACEWISE_DATA_MODE"):
        load_settings(path=False, env={"PLACEWISE_DATA_MODE": "sometimes"})
