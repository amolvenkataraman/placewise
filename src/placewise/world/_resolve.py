"""Shared by the world queries: dates, membership on a date, and not-found errors with suggestions."""

import datetime as dt
import difflib

from placewise.constants._keys import key


def day(value):
    """An ISO date string (YYYY-MM-DD) for a date, datetime or ISO string; today for None."""
    if value is None:
        return dt.date.today().isoformat()
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    try:
        return dt.date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        raise ValueError(f"{value!r} is not a date: give a datetime.date or 'YYYY-MM-DD'") from None


def active(membership, on):
    """Was the membership in force on `on` (YYYY-MM-DD)? A year alone covers the whole year:
    since "1949" counts from 1949-01-01, until "2000" to 2000-12-31; no dates means always."""
    since, until = membership.since, membership.until
    return (since is None or since <= on) and (until is None or f"{until}-12-31"[:10] >= on)


def not_found(what, text, names):
    """A KeyError naming `text` and the closest of `names` (suggestions compare normalised keys)."""
    by_key = {}
    for name in names:
        by_key.setdefault(key(name), name)
    close = difflib.get_close_matches(key(str(text)), list(by_key), n=3, cutoff=0.6)
    hint = f"; did you mean {', '.join(repr(by_key[k]) for k in close)}?" if close else ""
    return KeyError(f"no {what} {text!r}{hint}")
