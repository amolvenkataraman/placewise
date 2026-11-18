"""Changing one setting in placewise.toml (or placewise.json) in place: what `placewise data mode`
uses. The standard library reads TOML but can't write it, so a TOML file is edited line by line:
the key's line inside its [section] is replaced, or added under the section header, or a new
section is appended; comments and everything else stay as the user wrote them."""

import json
import os
import re
from pathlib import Path

from placewise.constants import config as const

from .errors import ConfigError
from .loader import config_dir, find_config
from .schema import FIELDS, SECTIONS

_HEADER = re.compile(r"^\s*\[\s*([A-Za-z0-9_-]+)\s*\]\s*(#.*)?$")
_ANY_HEADER = re.compile(r"^\s*\[")


def user_config_path(env=None):
    """The file `set_setting` should change: the config file in use if there is one, else
    placewise.toml in the per-user config directory."""
    found = find_config(env=os.environ if env is None else env)
    return found if found is not None else config_dir(env) / const.CONFIG_FILENAMES[0]


def set_setting(path, section, key, value):
    """Set `section.key = value` in the file at `path` (created if missing). The value is checked
    against the settings model first, so a bad value never reaches the file."""
    path = Path(path)
    if section not in SECTIONS or key not in FIELDS[section]:
        raise ConfigError(f"unknown setting {section}.{key}")
    try:
        SECTIONS[section].from_dict({key: value})
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{section}.{key}: {e}") from None
    if isinstance(value, tuple):
        value = list(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".json":
        doc = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        doc.setdefault(section, {})[key] = value
        _write(path, json.dumps(doc, indent=2) + "\n")
        return path
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    _write(path, _set_toml(text, section, key, _toml_value(value)))
    return path


def _set_toml(text, section, key, rendered):
    lines = text.splitlines()
    line = f"{key} = {rendered}"
    start = next((i for i, ln in enumerate(lines) if _section_of(ln) == section), None)
    if start is None:
        body = "\n".join(lines).rstrip("\n")
        return (body + "\n\n" if body else "") + f"[{section}]\n{line}\n"
    end = next((i for i in range(start + 1, len(lines)) if _ANY_HEADER.match(lines[i])), len(lines))
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
    for i in range(start + 1, end):
        if pattern.match(lines[i]):
            lines[i] = line
            break
    else:
        lines.insert(start + 1, line)
    return "\n".join(lines) + "\n"


def _section_of(line):
    match = _HEADER.match(line)
    return match.group(1) if match else None


def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return json.dumps(str(value))  # a JSON string is a valid TOML basic string


def _write(path, text):
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
