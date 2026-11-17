"""Shared behaviour of placewise's frozen dataclasses: plain-dict round trips.

The library returns these objects, the server serialises them with `to_dict`, and the client and
caches rebuild them with `from_dict`, so all three shapes stay identical.
"""

import dataclasses
import datetime as dt
import functools
import types
import typing
from enum import Enum


class Model:
    """Mixin for `@dataclass(frozen=True, slots=True)` types."""

    __slots__ = ()

    def to_dict(self):
        """JSON-ready dict in field order; None and empty collections are left out to keep it small."""
        out = {}
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if value is None or (isinstance(value, tuple | list | dict) and not value):
                continue
            out[f.name] = _plain(value)
        return out

    @classmethod
    def from_dict(cls, data):
        """Rebuild from `to_dict` output or a TOML / JSON document; unknown keys are an error."""
        if not isinstance(data, dict):
            raise ValueError(f"{cls.__name__} expects a mapping, got {type(data).__name__}")
        hints, known = _schema(cls)
        if unknown := sorted(set(data) - known):
            raise ValueError(f"{cls.__name__}: unknown field(s) {', '.join(unknown)}")
        return cls(**{k: _build(hints[k], v) for k, v in data.items()})


def set_field(obj, name, value):
    """Assign during __post_init__ of a frozen dataclass (normalising inputs)."""
    object.__setattr__(obj, name, value)


def _plain(value):
    if isinstance(value, Model):
        return value.to_dict()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, dt.date):  # datetimes too
        return value.isoformat()
    return value


def _build(tp, value):
    if value is None:
        return None
    origin, args = typing.get_origin(tp), typing.get_args(tp)
    if origin in (typing.Union, types.UnionType):
        for arg in args:
            if arg is type(None):
                continue
            try:
                return _build(arg, value)
            except (TypeError, ValueError):
                continue
        raise ValueError(f"{value!r} doesn't match {tp}")
    if origin is tuple:
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_build(args[0], v) for v in value)
        return tuple(_build(a, v) for a, v in zip(args, value, strict=True))
    if origin is dict:
        return {k: _build(args[1], v) for k, v in value.items()}
    if isinstance(tp, type):
        if isinstance(value, tp) and not (tp is int and isinstance(value, bool)):
            return value
        if issubclass(tp, Model):
            return tp.from_dict(value)
        if issubclass(tp, Enum):
            return tp(value)
        if tp is dt.datetime:
            return dt.datetime.fromisoformat(value)
        if tp is dt.date:
            return dt.date.fromisoformat(value)
        if tp in (float, int, str, bool):
            if tp is not str and isinstance(value, str):
                raise ValueError(f"expected {tp.__name__}, got text {value!r}")
            return tp(value)
    return value


@functools.cache
def _schema(cls):
    """Type hints and init field names of a model class, resolved once: resolving them per call
    dominated rebuilding large batches of results."""
    return typing.get_type_hints(cls), frozenset(f.name for f in dataclasses.fields(cls) if f.init)
