"""How Results and Entities show to people (constants: placewise.constants.display).

`str(result)` / `print(result)` is a readable text card: the label and coordinates, then one aligned
line per filled field with the source behind it at the right; `result.card(color=None)` adds ANSI
colour on a terminal. Jupyter shows `_repr_html_`, the same rows as a small table. `repr` stays
the exact dataclass form, which `eval` turns back into an equal object.
"""

from . import html, text
from .rows import card_rows

__all__ = ["card_rows", "html", "text"]
