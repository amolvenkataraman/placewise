"""The notebook view (`_repr_html_`): the card's rows as a small two-column table, sources in a third
dimmed column. No external assets and no colours of its own: text inherits the notebook theme's
colour and secondary text is dimmed with opacity, so it reads in light and dark themes alike."""

from html import escape

from .rows import card_rows

_TABLE = "border-collapse:collapse;margin:0;font-size:inherit;color:inherit;background:transparent"
_CAPTION = "caption-side:top;text-align:left;font-weight:600;padding:0 0 4px 0"
_KEY = "text-align:left;vertical-align:top;font-weight:normal;opacity:0.7;padding:1px 14px 1px 0"
_VALUE = "text-align:left;vertical-align:top;padding:1px 14px 1px 0"
_ASIDE = "font-weight:normal;opacity:0.7;padding-left:8px"
_SOURCE = "text-align:right;vertical-align:top;opacity:0.55;font-size:85%;padding:1px 0"


def card(obj):
    """An HTML table for a Result or an Entity."""
    (title, aside), rows = card_rows(obj)
    body = "".join(
        f'<tr><th style="{_KEY}">{escape(field)}</th><td style="{_VALUE}">{escape(value)}</td>'
        f'<td style="{_SOURCE}">{escape(source or "")}</td></tr>'
        for field, value, source in rows
    )
    kind = type(obj).__name__.lower()
    return (
        f'<table class="placewise-{kind}" style="{_TABLE}">'
        f'<caption style="{_CAPTION}">{escape(title)}{_aside(aside)}</caption><tbody>{body}</tbody></table>'
    )


def _aside(aside):
    return f'<span style="{_ASIDE}">{escape(aside)}</span>' if aside else ""
