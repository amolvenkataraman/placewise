"""Work mode from a description, a source's own value, or a location string. The phrases are
in `constants.work_modes`; `parse_location` reads the modes a location string names."""

import html
import re

from placewise.constants import work_modes as _rules
from placewise.constants.work_modes import HYBRID, ONSITE, REMOTE

from .parse import parse_location


def _compile(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)


_NEGATED = _compile(_rules.DESCRIPTION_NEGATED)
_HYBRID = _compile(_rules.DESCRIPTION_HYBRID)
_REMOTE = _compile(_rules.DESCRIPTION_REMOTE)
_ONSITE = _compile(_rules.DESCRIPTION_ONSITE)


_NOT_LOWER = re.compile(r"[^a-z]+")


def _words(value):
    return _NOT_LOWER.sub(" ", value.lower()).strip()


# every spelling, as words ("on site") and run together ("onsite")
_STRUCTURED = {
    form: mode
    for mode, values in _rules.STRUCTURED.items()
    for value in values
    for form in (_words(value), _words(value).replace(" ", ""))
}
_TAG = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t]+")


def structured_work_mode(value):
    """A source's own work-mode value ("OnSite", "REMOTE", "hybrid", True for "is remote") as
    "remote" / "hybrid" / "onsite", or None for values that say nothing ("unspecified")."""
    if value is True:
        return REMOTE
    if not isinstance(value, str):
        return None
    words = _words(value)
    return _STRUCTURED.get(words) or _STRUCTURED.get(words.replace(" ", ""))


def _plain(text):
    return _SPACES.sub(" ", html.unescape(_TAG.sub(" ", text)))


def detect_work_mode(text, location_hint="", structured=None):
    """ "remote", "hybrid", "onsite" or None for a listing. `structured` (the source's own value) wins
    when it says something; `location_hint` is the listing's location ("Remote - US"); `text` is the
    description, HTML or plain."""
    if (from_source := structured_work_mode(structured)) is not None:
        return from_source
    plain = _plain(text or "")
    unnegated = _NEGATED.sub(" ", plain)
    hint_modes = parse_location(location_hint).work_modes if location_hint else ()
    if _HYBRID.search(unnegated):
        return HYBRID
    if _REMOTE.search(unnegated):
        return REMOTE
    if REMOTE in hint_modes:
        return REMOTE
    if _ONSITE.search(plain):
        return ONSITE
    if HYBRID in hint_modes:
        return HYBRID
    return None
