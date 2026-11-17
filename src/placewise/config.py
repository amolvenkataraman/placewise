"""Loading Settings: shipped defaults < placewise.toml < environment < keyword arguments.

The file is the first that exists of: the `path` argument, $PLACEWISE_CONFIG, ./placewise.toml,
then <config dir>/placewise.toml (each location also accepts placewise.json, the same structure as
JSON, for Python 3.10 without tomli). The config dir is $XDG_CONFIG_HOME/placewise, else
~/.config/placewise (macOS ~/Library/Application Support/placewise, Windows %APPDATA%\\placewise).

Environment variables are PLACEWISE_<SECTION>_<KEY> (PLACEWISE_NEAR_AIRPORT=5,
PLACEWISE_WORLDVIEW_ORDER=IN,de_facto, PLACEWISE_DATA_OFFLINE=1), coerced to the field's type.
Keyword arguments are `section_key=value` or `section={key: value}`. Unknown sections or keys are
errors that name the key and where it came from, so a typo never silently does nothing.

Worldview lock: `[worldview] lock = true` is for operators with legal requirements to describe
disputed areas one way. Once a layer sets it, higher layers (environment, keyword arguments) may not
change anything in [worldview] (that raises WorldviewLockedError), and per-request orders are
ignored or rejected downstream (see `effective_worldview`).
"""

import dataclasses
import os
import sys
import types
import typing
from pathlib import Path

from placewise import _toml
from placewise.constants import config as const
from placewise.model import Settings

_SECTIONS = {f.name: typing.get_type_hints(Settings)[f.name] for f in dataclasses.fields(Settings)}
_FIELDS = {name: typing.get_type_hints(cls) for name, cls in _SECTIONS.items()}
_RANK = {"default": 0, "file": 1, "env": 2, "kwarg": 3}


class ConfigError(ValueError):
    """A configuration value, key or file is wrong; the message says which and where."""


class WorldviewLockedError(ConfigError):
    """Something tried to change a worldview the operator locked."""


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
        for section, fields in _FIELDS.items()
        for key in fields
    }


def effective_worldview(settings, requested=None):
    """(order, locked) for one request. Without a lock a requested order wins; with one the
    operator's order stands, and a different request is ignored (conflict = "ignore") or refused
    (conflict = "reject")."""
    view = settings.worldview
    wanted = tuple(requested) if requested else None
    if not view.lock:
        if wanted is None:
            return view.order, False
        return type(view)(order=wanted).order, False  # validates the request
    if wanted is not None and wanted != view.order and view.conflict == "reject":
        raise WorldviewLockedError(
            f"this instance's worldview is locked to {list(view.order)}; requested {list(wanted)}"
        )
    return view.order, True


# --- resolution ---------------------------------------------------------------------------------


def _resolve(path, env, overrides):
    env = os.environ if env is None else env
    defaults = Settings()
    sections = {name: {} for name in _SECTIONS}  # raw values set so far, per section
    values = {(s, k): getattr(getattr(defaults, s), k) for s, fields in _FIELDS.items() for k in fields}
    origins = dict.fromkeys(values, "default")
    lock = None  # (rank, origin) of the layer that locked the worldview

    layers = []
    cfg = find_config(path, env)
    if cfg is not None:
        layers.append(("file", _from_file(cfg)))
    layers.append(("env", _from_env(env)))
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

    settings = Settings(**{name: cls.from_dict(sections[name]) for name, cls in _SECTIONS.items()})
    return settings, origins


def _check(current, section, key, raw, origin):
    """The validated value of one setting, given the others already set in its section."""
    try:
        built = _SECTIONS[section].from_dict({**current, key: raw})
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
        if section not in _SECTIONS:
            raise ConfigError(f"{path}: unknown section [{section}]; known: {', '.join(_SECTIONS)}")
        if not isinstance(table, dict):
            raise ConfigError(f"{path}: [{section}] must be a table of settings, not a single value")
        for key, raw in table.items():
            if key not in _FIELDS[section]:
                raise ConfigError(
                    f"{path}: unknown key {section}.{key}; [{section}] has {', '.join(_FIELDS[section])}"
                )
            entries.append(((section, key), raw, origin))
    return entries


def _from_env(env):
    found = {}
    # aliases first, so the full PLACEWISE_<SECTION>_<KEY> spelling wins when both are set
    for name in sorted(env, key=lambda n: n not in const.ENV_ALIASES):
        if not name.startswith(const.ENV_PREFIX) or name in const.ENV_RESERVED:
            continue
        if name in const.ENV_ALIASES:
            section, key = const.ENV_ALIASES[name]
        else:
            section, _, key = name[len(const.ENV_PREFIX) :].lower().partition("_")
            if section not in _SECTIONS:
                raise ConfigError(
                    f"unknown environment variable {name}: no [{section}] section "
                    f"(known: {', '.join(_SECTIONS)}); settings are PLACEWISE_<SECTION>_<KEY>"
                )
            if key not in _FIELDS[section]:
                raise ConfigError(
                    f"unknown environment variable {name}: [{section}] has no key {key!r} "
                    f"(known: {', '.join(_FIELDS[section])})"
                )
        try:
            value = _coerce(_FIELDS[section][key], env[name])
        except ValueError as e:
            raise ConfigError(f"{name}={env[name]!r}: {e}") from None
        found[(section, key)] = (value, f"env:{name}")
    return [(target, value, origin) for target, (value, origin) in found.items()]


def _from_kwargs(overrides):
    entries = []
    for name, value in overrides.items():
        if name in _SECTIONS and isinstance(value, dict):
            for key, raw in value.items():
                if key not in _FIELDS[name]:
                    raise ConfigError(f"unknown setting {name}.{key} in keyword argument {name}=")
                entries.append(((name, key), _kwarg_value(name, key, raw), f"kwarg:{name}"))
            continue
        section, _, key = name.partition("_")
        if section not in _SECTIONS or key not in _FIELDS[section]:
            raise ConfigError(f"unknown setting {name!r}; use section_key=value, e.g. near_airport=5")
        entries.append(((section, key), _kwarg_value(section, key, value), f"kwarg:{name}"))
    return entries


def _kwarg_value(section, key, value):
    tp = _FIELDS[section][key]
    if isinstance(value, str) and _base(tp) is not str:
        try:
            return _coerce(tp, value)
        except ValueError as e:
            raise ConfigError(f"keyword {section}_{key}={value!r}: {e}") from None
    return value


def _base(tp):
    """The non-None type of an optional, else tp itself."""
    if typing.get_origin(tp) in (typing.Union, types.UnionType):
        return next(arg for arg in typing.get_args(tp) if arg is not type(None))
    return tp


def _coerce(tp, text):
    """A setting's value from environment text, by the field's declared type."""
    optional = _base(tp) is not tp
    base = _base(tp)
    text = text.strip()
    if optional and text == "":
        return None
    if base is bool:
        word = text.lower()
        if word in const.TRUE_WORDS:
            return True
        if word in const.FALSE_WORDS:
            return False
        raise ValueError(f"expected one of {sorted(const.TRUE_WORDS | const.FALSE_WORDS)}")
    if base is int:
        try:
            return int(text)
        except ValueError:
            raise ValueError("expected a whole number") from None
    if base is float:
        try:
            return float(text)
        except ValueError:
            raise ValueError("expected a number") from None
    if typing.get_origin(base) is tuple:
        return tuple(part.strip() for part in text.split(const.LIST_SEPARATOR) if part.strip())
    return text
