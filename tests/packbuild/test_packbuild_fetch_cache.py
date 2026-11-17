"""Where packbuild caches downloads and writes packs: ~/.placewise/packbuild unless configured."""

import importlib
from pathlib import Path

from packbuild import fetch


def _reloaded(monkeypatch, **env):
    monkeypatch.delenv(fetch.ENV_CACHE, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return importlib.reload(fetch)


def test_default_cache_is_under_dot_placewise(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        assert _reloaded(monkeypatch).DEFAULT_CACHE == tmp_path / ".placewise" / "packbuild"
    finally:
        monkeypatch.undo()
        importlib.reload(fetch)


def test_environment_variable_overrides_the_cache(monkeypatch, tmp_path):
    try:
        assert _reloaded(monkeypatch, PACKBUILD_CACHE=str(tmp_path / "c")).DEFAULT_CACHE == tmp_path / "c"
    finally:
        monkeypatch.undo()
        importlib.reload(fetch)


def test_the_variable_is_not_a_placewise_runtime_setting():
    assert not fetch.ENV_CACHE.startswith("PLACEWISE_")
    assert isinstance(fetch.DEFAULT_CACHE, Path)
