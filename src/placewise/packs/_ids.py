"""Derived ids (docs/pack-format.md, "Derived ids"): a layer's `id` built from its other string
fields by a template, so the pack needn't store a string per row ("postal:{country}:{name}").

`IdTemplate` is what a builder asks for. `encode` (writer) renders it for every row, checks it
against the real ids and keeps the rows it doesn't fit as exceptions, or gives up on a template
that fits too few rows. `DerivedIds` (reader) answers one row's id, or every row's, from the
stored columns, the same strings the writer was given.
"""

import re
from dataclasses import dataclass

import numpy as np

from placewise.constants import packs as consts

from ._lazy import once

_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)(?::([A-Za-z_]+))?\}")
_TRANSFORMS = {
    "compact": lambda s: s.replace(" ", "").replace("-", ""),  # "100 01", "100-01" -> "10001"
    "tail": lambda s: s.rpartition(":")[2],  # "geonames:123" -> "123"
}


@dataclass(frozen=True, slots=True)
class IdTemplate:
    """How a layer's ids are made from its other string fields.

    text    literal text with {field} or {field:transform} placeholders, each a str field of the
            layer other than id; transforms: `compact` drops spaces and hyphens, `tail` keeps the
            text after the last colon
    repeat  appended to the n-th row (n >= 2, counting in row order) whose placeholder fields
            hold the same values as an earlier row's, with {n} replaced by n; "" for none
    """

    text: str
    repeat: str = ""

    def parts(self):
        """(literals, placeholders): the text around the placeholders (one more than them) and
        each placeholder's (field, transform or None). ValueError for a malformed template."""
        literals, fields, at = [], [], 0
        for m in _PLACEHOLDER.finditer(self.text):
            literals.append(self.text[at : m.start()])
            fields.append((m.group(1), m.group(2)))
            at = m.end()
        literals.append(self.text[at:])
        if any("{" in s or "}" in s for s in literals):
            raise ValueError(f"id template {self.text!r}: unbalanced or malformed braces")
        for _, transform in fields:
            if transform is not None and transform not in _TRANSFORMS:
                raise ValueError(
                    f"id template {self.text!r}: unknown transform {transform!r} "
                    f"(known: {', '.join(_TRANSFORMS)})"
                )
        rest = self.repeat.replace(consts.ID_REPEAT_NUMBER, "", 1)
        if self.repeat and (consts.ID_REPEAT_NUMBER not in self.repeat or "{" in rest or "}" in rest):
            raise ValueError(f"id template repeat {self.repeat!r} must hold {consts.ID_REPEAT_NUMBER} once")
        return literals, fields

    def renderer(self):
        """A function from the placeholder fields' values (a sequence, in template order) to the
        id before any repeat suffix."""
        literals, fields = self.parts()
        steps = [(_TRANSFORMS.get(t), lit) for (_, t), lit in zip(fields, literals[1:], strict=True)]
        head = literals[0]

        def render(values):
            out = [head]
            for (fn, lit), v in zip(steps, values, strict=True):
                out += (fn(v) if fn else v, lit)
            return "".join(out)

        return render

    def suffix(self, n):
        """The repeat text of the n-th row with the same values ("" for the first)."""
        return self.repeat.replace(consts.ID_REPEAT_NUMBER, str(n)) if n > 1 and self.repeat else ""


def occurrences(keys, count):
    """For each row, 1 + how many earlier rows hold the same values in every one of `keys` (int
    arrays, one per placeholder; equal ints are equal values). All rows match when there are none."""
    if not keys:
        return np.arange(1, count + 1, dtype=np.int64)
    keys = [np.asarray(k, dtype=np.int64) for k in keys]
    sizes = [int(k.max()) + 1 if count else 1 for k in keys]
    if count and min(int(k.min()) for k in keys) >= 0 and np.prod(sizes, dtype=float) < 2.0**62:
        one = keys[0]
        for k, size in zip(keys[1:], sizes[1:], strict=True):
            one = one * size + k
        keys = [one]  # the same groups, sorted in one pass
    # stable: row order within a group
    order = np.argsort(keys[0], kind="stable") if len(keys) == 1 else np.lexsort(keys[::-1])
    same = np.ones(max(count - 1, 0), dtype=bool)  # sorted row j + 1 holds row j's values
    for k in keys:
        sorted_k = np.asarray(k)[order]
        same &= sorted_k[1:] == sorted_k[:-1]
    pos = np.arange(count, dtype=np.int64)
    start = np.maximum.accumulate(np.where(np.concatenate([[True], ~same]), pos, 0)) if count else pos
    out = np.empty(count, dtype=np.int64)
    out[order] = pos - start + 1
    return out


def encode(where, template, ids, strings):
    """The id field's layer.json entry and the exception rows (rows whose id the template doesn't
    give, an int32 array), or None when it fits too few rows to be worth it. `strings`: the layer's
    str columns, {field: list of str, "" for null}."""
    try:
        _, fields = template.parts()
    except ValueError as err:
        raise ValueError(f"{where}: {err}") from None
    for f, _ in fields:
        if f == "id" or f not in strings:
            raise ValueError(f"{where}: id template {template.text!r} names no str field {f!r}")
    columns = [strings[f] for f, _ in fields]
    n = None
    if template.repeat:  # each distinct value as an int, for occurrences
        keys = []
        for col in columns:
            first = {}
            keys.append(np.fromiter((first.setdefault(v, len(first)) for v in col), np.int64, len(ids)))
        n = occurrences(keys, len(ids))
    derived = _render_all(template, columns, n, len(ids))
    rows = np.array([i for i, (a, b) in enumerate(zip(derived, ids, strict=True)) if a != b], dtype=np.int32)
    if len(rows) > consts.ID_MAX_EXCEPTION_SHARE * len(ids):
        return None
    spec = {"type": "str", "template": template.text}
    if template.repeat:
        spec["repeat"] = template.repeat
    spec["exceptions"] = len(rows)
    return spec, rows


def _render_all(template, columns, n, count):
    """Every row's id from the placeholder fields' values (`columns`, in template order) and the
    rows' occurrences `n` (None without a repeat)."""
    render = template.renderer()
    out = [render(values) for values in zip(*columns, strict=True)] if columns else [render(())] * count
    if n is not None:
        for i in np.flatnonzero(n > 1).tolist():
            out[i] += template.suffix(int(n[i]))
    return out


class DerivedIds:
    """A layer's ids from its id template (layer.json `fields.id`): what the writer was given."""

    def __init__(self, layer, spec):
        self.layer = layer
        self.template = IdTemplate(spec["template"], spec.get("repeat", ""))
        self.fields = [f for f, _ in self.template.parts()[1]]
        self.render = self.template.renderer()
        self.exceptions = int(spec.get("exceptions", 0))

    def value(self, i):
        """Row i's id (i already in range)."""
        if self.exceptions and (k := self._exception_of.get(i)) is not None:
            return self.layer._string(k)
        string = self.layer._string
        ident = self.render([string(int(codes[i])) for codes in self._columns])
        return ident + self.template.suffix(int(self._occurrences[i])) if self.template.repeat else ident

    def column(self):
        """Every row's id, as a list."""
        columns = [self.layer.column(f) for f in self.fields]
        n = self._occurrences if self.template.repeat else None
        out = _render_all(self.template, columns, n, self.layer.count)
        rows, ids = self._exceptions
        for r, s in zip(rows.tolist(), self.layer._strings_of(ids).tolist(), strict=True):
            out[r] = s
        return out

    def _codes(self, field):
        return self.layer._array(f"{consts.COL_DIR}/{field}.npy")

    @once
    def _columns(self):
        return [np.asarray(self._codes(f)) for f in self.fields]  # plain arrays: faster to index

    @once
    def _occurrences(self):
        return occurrences(self._columns, self.layer.count)

    @once
    def _exception_of(self):
        rows, ids = self._exceptions
        return dict(zip(rows.tolist(), ids.tolist(), strict=True))

    @once
    def _exceptions(self):
        if not self.exceptions:
            return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)
        rows = np.asarray(self.layer._array(f"{consts.COL_DIR}/{consts.ID_EXCEPTION_ROWS}.npy"))
        return rows, np.asarray(self.layer._array(f"{consts.COL_DIR}/{consts.ID_EXCEPTION_IDS}.npy"))
