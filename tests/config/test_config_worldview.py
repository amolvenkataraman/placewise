"""placewise.config.worldview: the operator's worldview lock, at load time and per request."""

import pytest
from config_kit import write_json

from placewise.config import WorldviewLockedError, effective_worldview, load_settings
from placewise.model import Settings


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
