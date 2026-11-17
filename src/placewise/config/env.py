"""Settings from environment variables: PLACEWISE_<SECTION>_<KEY> (or an alias), coerced from text
to the field's declared type."""

import types
import typing

from placewise.constants import config as const

from .errors import ConfigError
from .schema import FIELDS, SECTIONS


def from_env(env):
    """[((section, key), value, origin)] for every PLACEWISE_ variable in `env`."""
    found = {}
    ours = [name for name in env if name.startswith(const.ENV_PREFIX)]  # the rest are never read
    # aliases first, so the full PLACEWISE_<SECTION>_<KEY> spelling wins when both are set
    for name in sorted(ours, key=lambda n: n not in const.ENV_ALIASES):
        if name in const.ENV_RESERVED:
            continue
        if name in const.ENV_ALIASES:
            section, key = const.ENV_ALIASES[name]
        else:
            section, _, key = name[len(const.ENV_PREFIX) :].lower().partition("_")
            if section not in SECTIONS:
                raise ConfigError(
                    f"unknown environment variable {name}: no [{section}] section "
                    f"(known: {', '.join(SECTIONS)}); settings are PLACEWISE_<SECTION>_<KEY>"
                )
            if key not in FIELDS[section]:
                raise ConfigError(
                    f"unknown environment variable {name}: [{section}] has no key {key!r} "
                    f"(known: {', '.join(FIELDS[section])})"
                )
        try:
            value = coerce(FIELDS[section][key], env[name])
        except ValueError as e:
            raise ConfigError(f"{name}={env[name]!r}: {e}") from None
        found[(section, key)] = (value, f"env:{name}")
    return [(target, value, origin) for target, (value, origin) in found.items()]


def base(tp):
    """The non-None type of an optional, else tp itself."""
    if typing.get_origin(tp) in (typing.Union, types.UnionType):
        return next(arg for arg in typing.get_args(tp) if arg is not type(None))
    return tp


def coerce(tp, text):
    """A setting's value from environment text, by the field's declared type."""
    optional = base(tp) is not tp
    base_tp = base(tp)
    text = text.strip()
    if optional and text == "":
        return None
    if base_tp is bool:
        word = text.lower()
        if word in const.TRUE_WORDS:
            return True
        if word in const.FALSE_WORDS:
            return False
        raise ValueError(f"expected one of {sorted(const.TRUE_WORDS | const.FALSE_WORDS)}")
    if base_tp is int:
        try:
            return int(text)
        except ValueError:
            raise ValueError("expected a whole number") from None
    if base_tp is float:
        try:
            return float(text)
        except ValueError:
            raise ValueError("expected a number") from None
    if typing.get_origin(base_tp) is tuple:
        return tuple(part.strip() for part in text.split(const.LIST_SEPARATOR) if part.strip())
    return text
