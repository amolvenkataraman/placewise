"""Loading Settings: shipped defaults < placewise.toml < environment < keyword arguments.

The file is the first that exists of: the `path` argument, $PLACEWISE_CONFIG, ./placewise.toml,
then <config dir>/placewise.toml (each location also accepts placewise.json, the same structure as
JSON, for Python 3.10 without tomli). The config dir is $XDG_CONFIG_HOME/placewise, else
~/.config/placewise (macOS ~/Library/Application Support/placewise, Windows %APPDATA%\\placewise).

Environment variables are PLACEWISE_<SECTION>_<KEY> (PLACEWISE_NEAR_AIRPORT=5,
PLACEWISE_WORLDVIEW_ORDER=IN,de_facto, PLACEWISE_DATA_OFFLINE=1), coerced to the field's type.
Keyword arguments are `section_key=value` or `section={key: value}`. Unknown sections or keys are
errors that name the key and where it came from, so a typo never silently does nothing; every
PLACEWISE_* variable but PLACEWISE_CONFIG and PLACEWISE_KEYS_FILE is read as a setting, so apps
must give their own variables another prefix (README, "Settings").

Worldview lock: `[worldview] lock = true` is for operators with legal requirements to describe
disputed areas one way. Once a layer sets it, higher layers (environment, keyword arguments) may not
change anything in [worldview] (that raises WorldviewLockedError), and per-request orders are
ignored or rejected downstream (see `effective_worldview`).
"""

import os
import sys
from pathlib import Path

from placewise.constants import config as const
from placewise.model import Settings

from . import _toml
from .env import base, coerce, from_env
from .errors import ConfigError
from .schema import FIELDS, SECTIONS
from .worldview import WorldviewLockedError

_RANK = {"default": 0, "file": 1, "env": 2, "kwarg": 3}


def config_dir(env=None, platform=None):
    """The per-user config directory placewise looks in for placewise.toml."""
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    xdg = env.get("XDG_CONFIG_HOME")
    if xdg and os.path.isabs(xdg):  # the XDG spec says relative values are invalid
        return Path(xdg) / const.APP_DIR_NAME
    if platform == "win32":
        appdata = env.get("APPDATA")
        return (Path(appdata) if appdata else Path.home() / "AppData" / "Roaming") / const.APP_DIR_NAME
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / const.APP_DIR_NAME
    return Path.home() / ".config" / const.APP_DIR_NAME


def find_config(path=None, env=None):
    """The config file to read, or None. `path=False` means read no file. A file named explicitly
    (argument or $PLACEWISE_CONFIG) must exist."""
    env = os.environ if env is None else env
    if path is False:
        return None
    if path is not None:
        found = Path(path).expanduser()
        if not found.is_file():
            raise ConfigError(f"config file not found: {found}")
        return found
    if named := env.get(const.ENV_CONFIG):
        found = Path(named).expanduser()
        if not found.is_file():
            raise ConfigError(f"{const.ENV_CONFIG} points at a missing file: {found}")
        return found
    for directory in (Path.cwd(), config_dir(env)):
        for name in const.CONFIG_FILENAMES:
            if (directory / name).is_file():
                return directory / name
    return None


def load_settings(path=None, env=os.environ, **overrides):
    """Settings from defaults, the config file, the environment and keyword arguments, in that order."""
    return _resolve(path, env, overrides)[0]


def explain_settings(path=None, env=os.environ, **overrides):
    """{"section.key": (value, origin)} for every setting. Origins: "default", "file:<path>",
    "env:<VARIABLE>", "kwarg:<name>"."""
    settings, origins = _resolve(path, env, overrides)
    return {
        f"{section}.{key}": (getattr(getattr(settings, section), key), origins[(section, key)])
        for section, fields in FIELDS.items()
        for key in fields
    }


# --- resolution ---------------------------------------------------------------------------------


def _resolve(path, env, overrides):
    env = os.environ if env is None else env
    defaults = Settings()
    sections = {name: {} for name in SECTIONS}  # raw values set so far, per section
    values = {(s, k): getattr(getattr(defaults, s), k) for s, fields in FIELDS.items() for k in fields}
    origins = dict.fromkeys(values, "default")
    lock = None  # (rank, origin) of the layer that locked the worldview

    layers = []
    cfg = find_config(path, env)
    if cfg is not None:
        layers.append(("file", _from_file(cfg)))
    layers.append(("env", from_env(env)))
    layers.append(("kwarg", _from_kwargs(overrides)))

    for kind, entries in layers:
        for (section, key), raw, origin in entries:
            value = _check(sections[section], section, key, raw, origin)
            if lock and section == "worldview" and _RANK[kind] > lock[0] and value != values[(section, key)]:
                raise WorldviewLockedError(
                    f"{origin} tries to change worldview.{key}, but the worldview is locked by "
                    f"{lock[1]}; the lock is for operators with legal requirements, so only that "
                    "file can change it"
                )
            sections[section][key] = raw
            values[(section, key)] = value
            origins[(section, key)] = origin
        if lock is None and values[("worldview", "lock")]:
            lock = (_RANK[kind], origins[("worldview", "lock")])

    settings = Settings(**{name: cls.from_dict(sections[name]) for name, cls in SECTIONS.items()})
    return settings, origins


def _check(current, section, key, raw, origin):
    """The validated value of one setting, given the others already set in its section."""
    try:
        built = SECTIONS[section].from_dict({**current, key: raw})
    except (TypeError, ValueError) as e:
        raise ConfigError(f"{origin}: {section}.{key}: {e}") from None
    return getattr(built, key)


def _from_file(path):
    try:
        doc = _toml.load(path)
    except _toml.TomlUnavailableError:
        raise
    except ValueError as e:
        raise ConfigError(str(e)) from None
    origin = f"file:{path}"
    entries = []
    for section, table in doc.items():
        if section not in SECTIONS:
            raise ConfigError(f"{path}: unknown section [{section}]; known: {', '.join(SECTIONS)}")
        if not isinstance(table, dict):
            raise ConfigError(f"{path}: [{section}] must be a table of settings, not a single value")
        for key, raw in table.items():
            if key not in FIELDS[section]:
                raise ConfigError(
                    f"{path}: unknown key {section}.{key}; [{section}] has {', '.join(FIELDS[section])}"
                )
            entries.append(((section, key), raw, origin))
    return entries


def _from_kwargs(overrides):
    entries = []
    for name, value in overrides.items():
        if name in SECTIONS and isinstance(value, dict):
            for key, raw in value.items():
                if key not in FIELDS[name]:
                    raise ConfigError(f"unknown setting {name}.{key} in keyword argument {name}=")
                entries.append(((name, key), _kwarg_value(name, key, raw), f"kwarg:{name}"))
            continue
        section, _, key = name.partition("_")
        if section not in SECTIONS or key not in FIELDS[section]:
            raise ConfigError(f"unknown setting {name!r}; use section_key=value, e.g. near_airport=5")
        entries.append(((section, key), _kwarg_value(section, key, value), f"kwarg:{name}"))
    return entries


def _kwarg_value(section, key, value):
    tp = FIELDS[section][key]
    if isinstance(value, str) and base(tp) is not str:
        try:
            return coerce(tp, value)
        except ValueError as e:
            raise ConfigError(f"keyword {section}_{key}={value!r}: {e}") from None
    return value
