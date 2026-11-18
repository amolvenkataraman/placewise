"""The text card: the title line, then one aligned line per filled field with its source at the
right edge, at most `width` columns. Plain text unless asked for colour; `use_color(None)` decides
for the terminal (sys.stdout a TTY, NO_COLOR unset)."""

import os
import sys

from placewise.constants import display as const

from .rows import card_rows


def card(obj, color=False, width=const.WIDTH):
    """The card of a Result or an Entity. color: True, False, or None to colour only on a terminal."""
    (title, aside), rows = card_rows(obj)
    colored = use_color(color)
    if aside and title:  # the label gives way to its coordinates
        aside = _fit(aside, width)
        title = _fit(title, width - len(aside) - const.GAP)
        lines = [_style(title, const.BOLD, colored) + " " * const.GAP + aside]
    else:
        lines = [_style(_fit(title or aside, width), const.BOLD, colored)]
    if rows:
        key_width = max(len(f) for f, _, _ in rows)
        prefix = len(const.INDENT) + key_width + 1
        laid = [_lay(f, v, s, prefix, width) for f, v, s in rows]
        right = max(len(v) + (const.GAP + len(s) if s else 0) for _, v, s in laid) + prefix
        for field, value, source in laid:
            key = _style(field.ljust(key_width), const.KEY, colored)
            line = f"{const.INDENT}{key} "
            if source:
                pad = right - prefix - len(value) - len(source)
                line += value + " " * pad + _style(source, const.DIM, colored)
            else:
                line += value
            lines.append(line)
    return "\n".join(lines)


def use_color(color):
    """Whether to write ANSI colour: as asked, or (None) when stdout is a terminal and NO_COLOR is unset."""
    if color is not None:
        return bool(color)
    if os.environ.get(const.NO_COLOR_ENV):
        return False
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):  # replaced or closed streams
        return False


def _lay(field, value, source, prefix, width):
    """(field, value, source) fitted into width: the source dropped if the value would get too
    narrow, the value cut with an ellipsis."""
    room = width - prefix
    if source and room - const.GAP - len(source) < min(const.MIN_VALUE, len(value)):
        source = None
    if source:
        room -= const.GAP + len(source)
    return field, _fit(value, room), source


def _fit(text, room):
    return text if len(text) <= room else text[: max(room - 1, 0)].rstrip() + const.ELLIPSIS


def _style(text, code, colored):
    return f"{code}{text}{const.RESET}" if colored and text else text
