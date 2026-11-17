"""Reading TOML, or JSON with the same structure.

Python 3.11+ ships `tomllib`. On 3.10 placewise uses `tomli` if it is installed, and otherwise says
so clearly; the runtime stays numpy-only, so JSON files (same tables, same keys) are the
zero-dependency path there.
"""

import json
from pathlib import Path


class TomlUnavailableError(ImportError):
    """No TOML parser: Python 3.10 without tomli."""


def toml_module():
    """`tomllib` (3.11+), else `tomli`, else TomlUnavailableError."""
    try:
        import tomllib

        return tomllib
    except ImportError:
        pass
    try:
        import tomli

        return tomli
    except ImportError:
        raise TomlUnavailableError(
            "reading TOML needs Python 3.11+ (tomllib) or `pip install tomli`; "
            "or write the same structure as JSON (a .json file)"
        ) from None


def available():
    """Whether TOML can be read here."""
    try:
        toml_module()
    except TomlUnavailableError:
        return False
    return True


def loads(text, fmt="toml", source="<string>"):
    """Parse TOML or JSON text into a dict; syntax errors name `source`."""
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise ValueError(f"{source}: invalid JSON: {e}") from None
        if not isinstance(data, dict):
            raise ValueError(f"{source}: expected a JSON object at the top level, got {type(data).__name__}")
        return data
    if fmt != "toml":
        raise ValueError(f"unknown format {fmt!r}; expected 'toml' or 'json'")
    toml = toml_module()
    try:
        return toml.loads(text)
    except toml.TOMLDecodeError as e:
        raise ValueError(f"{source}: invalid TOML: {e}") from None


def load(path):
    """A .json file as JSON, anything else as TOML."""
    path = Path(path)
    fmt = "json" if path.suffix.lower() == ".json" else "toml"
    if fmt == "toml":
        try:
            toml_module()
        except TomlUnavailableError as e:
            raise TomlUnavailableError(f"{path}: {e}") from None
    return loads(path.read_text(encoding="utf-8"), fmt, source=str(path))
