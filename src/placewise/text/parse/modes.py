"""Work-mode phrases in a location string ("Remote", "Hybrid (3 days/week)", "On-site")."""

import re

from placewise.constants.work_modes import HYBRID, ONSITE, REMOTE

from .patterns import ANY_MODE, NEGATED_REMOTE, NUMBER_WORDS, OFFICE_DAYS, OFFICE_WEEKDAYS, WEEKLY_DAYS
from .patterns import HYBRID as HYBRID_PATTERN
from .patterns import ONSITE as ONSITE_PATTERN
from .patterns import REMOTE as REMOTE_PATTERN

_COUNTS = re.compile(r"\b(?:[1-5]|one|two|three|four|five)\b", re.IGNORECASE)


def _work_modes(text, start, end):
    """Modes named in text[start:end], blanking each phrase; and the spans of remote phrases."""
    chunk = text.get(start, end)
    found, remote_spans = set(), []
    if ANY_MODE.hopeless(chunk):
        return found, remote_spans
    for m in OFFICE_DAYS.finditer(chunk):
        numbers = [int(n) if n.isdigit() else NUMBER_WORDS[n.lower()] for n in _COUNTS.findall(m.group())]
        found.add(ONSITE if numbers and max(numbers) >= 5 else HYBRID)
        text.blank(start + m.start(), start + m.end())
    chunk = text.get(start, end)
    if found or HYBRID_PATTERN.search(chunk) or ONSITE_PATTERN.search(chunk):  # "Hybrid (3 days/week)"
        for m in WEEKLY_DAYS.finditer(chunk):
            text.blank(start + m.start(), start + m.end())
        chunk = text.get(start, end)
    for pattern, mode in (
        (OFFICE_WEEKDAYS, HYBRID),
        (NEGATED_REMOTE, ONSITE),
        (HYBRID_PATTERN, HYBRID),
        (REMOTE_PATTERN, REMOTE),
        (ONSITE_PATTERN, ONSITE),
    ):
        for m in pattern.finditer(chunk):
            found.add(mode)
            if mode == REMOTE:
                remote_spans.append((start + m.start(), start + m.end()))
            text.blank(start + m.start(), start + m.end())
        chunk = text.get(start, end)
    return found, remote_spans
