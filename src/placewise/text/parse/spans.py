"""The working copy of a location string, and splitting it while offsets into the raw text survive."""

import re
from dataclasses import dataclass

from placewise.constants._keys import key

from .readings import _and_names


@dataclass
class _Text:
    """The working copy of the raw string; same length, so spans stay valid as text is blanked."""

    chars: list

    def get(self, start, end):
        return "".join(self.chars[start:end])

    def blank(self, start, end):
        self.chars[start:end] = [" "] * (end - start)


def _trim(text, start, end):
    """(start, end) with surrounding whitespace removed."""
    chunk = text.get(start, end)
    stripped = chunk.strip()
    if not stripped:
        return start, start
    lead = len(chunk) - len(chunk.lstrip())
    return start + lead, start + lead + len(stripped)


def _split(text, start, end, pattern, keep=None):
    """Spans between matches of `pattern` in text[start:end], outside parentheses; `keep(match)`
    returning True skips a separator."""
    chunk = text.get(start, end)
    depth, inside = 0, []
    for c in chunk:
        depth += c == "("
        inside.append(depth > 0)
        depth -= c == ")" and depth > 0
    spans, last = [], 0
    for m in pattern.finditer(chunk):
        if m.end() == m.start() and m.start() in (0, len(chunk)):
            continue
        if inside[m.start()] or (keep and keep(chunk, m)):
            continue
        spans.append((start + last, start + m.start()))
        last = m.end()
    spans.append((start + last, end))
    return [s for s in spans if s[1] > s[0]]


def _protected_and(chunk, m):
    """Is this " and " / "&" inside a name such as "Trinidad and Tobago"?"""
    sep = m.group().strip().lower()
    if sep not in {"and", "&"}:
        return False
    left = re.findall(r"[\w'.]+", chunk[: m.start()])[-8:]
    right = re.findall(r"[\w'.]+", chunk[m.end() :])[:8]
    names = _and_names()
    for i in range(len(left)):
        for j in range(1, len(right) + 1):
            if key(" ".join([*left[i:], "and", *right[:j]])) in names:
                return True
    return False
