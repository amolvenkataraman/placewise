"""placewise._toml: TOML via tomllib / tomli, JSON with the same structure, and a clear error on 3.10."""

import importlib.util
import json
import sys

import pytest

from placewise import _toml

HAS_TOML = any(importlib.util.find_spec(name) for name in ("tomllib", "tomli"))
needs_toml = pytest.mark.skipif(not HAS_TOML, reason="needs tomllib (3.11+) or tomli")

DOC = {"alias": [{"text": "GTA", "means": "placewise:region/gta"}], "near": {"airport": 5.0}}


@needs_toml
def test_toml_file_loads(tmp_path):
    path = tmp_path / "a.toml"
    path.write_text('[[alias]]\ntext = "GTA"\nmeans = "placewise:region/gta"\n\n[near]\nairport = 5.0\n')
    assert _toml.load(path) == DOC
    assert _toml.available()


def test_json_file_with_the_same_structure_loads(tmp_path):
    path = tmp_path / "a.json"
    path.write_text(json.dumps(DOC))
    assert _toml.load(path) == DOC


def test_json_must_be_an_object(tmp_path):
    path = tmp_path / "a.json"
    path.write_text("[1, 2]")
    with pytest.raises(ValueError, match=r"a\.json"):
        _toml.load(path)


def test_syntax_errors_name_the_file(tmp_path):
    bad_json = tmp_path / "broken.json"
    bad_json.write_text("{nope")
    with pytest.raises(ValueError, match=r"broken\.json"):
        _toml.load(bad_json)
    if HAS_TOML:
        bad_toml = tmp_path / "broken.toml"
        bad_toml.write_text("x = = 1")
        with pytest.raises(ValueError, match=r"broken\.toml"):
            _toml.load(bad_toml)


def test_without_tomllib_or_tomli_toml_raises_a_clear_error(tmp_path, monkeypatch):
    # a None entry in sys.modules makes `import name` raise ImportError, as on 3.10 without tomli
    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", None)
    path = tmp_path / "a.toml"
    path.write_text('x = "1"\n')
    assert not _toml.available()
    with pytest.raises(_toml.TomlUnavailableError, match=r"3\.11.*pip install tomli") as info:
        _toml.load(path)
    assert "JSON" in str(info.value)
    assert isinstance(info.value, ImportError)
    # JSON still works with no TOML parser at all
    j = tmp_path / "a.json"
    j.write_text('{"x": "1"}')
    assert _toml.load(j) == {"x": "1"}


def test_tomli_is_used_when_tomllib_is_missing(monkeypatch):
    class FakeTomli:
        TOMLDecodeError = ValueError

        @staticmethod
        def loads(text):
            return {"via": "tomli"}

    monkeypatch.setitem(sys.modules, "tomllib", None)
    monkeypatch.setitem(sys.modules, "tomli", FakeTomli)
    assert _toml.loads("anything") == {"via": "tomli"}
