"""The name index every pack carries (docs/pack-format.md, "Name index"), built from the pack's
own layers by a small spec per layer: which columns hold names, pipe-separated aliases and exact
codes, what kind of place a row is and how prominent (rank). Every pack builder ends with

    write_pack(out_dir, name, version, layers, names=names.for_pack("world", layers))

The specs per pack are in packbuild/name_specs.py. Ids need no spec: the writer indexes the id of
every row of every indexed layer.
"""

import math
import re
from dataclasses import dataclass, field

import numpy as np

from placewise.packs import NameData

# an alias written as a short run of capitals and digits is an abbreviation ("GTA", "NYC", "SF")
_ABBREVIATION = re.compile(r"[A-Z][A-Z0-9&.]{1,5}")
_TEMPLATE = re.compile(r"\{(\w+)\}")
_NO_CODE = frozenset({"", "-99", "-1"})  # Natural Earth's "none"


@dataclass(frozen=True)
class Term:
    """One part of a rank: span * s, s in [0, 1] from a column. scale "log" maps log10(value + 1)
    from [lo, hi]; "linear" maps value from [lo, hi]; "invert" maps it from [hi, lo] (a tier or a
    scalerank, small = prominent); "values" looks the value up in `values`. Nulls give 0."""

    column: str
    span: float
    lo: float = 0.0
    hi: float = 9.0
    scale: str = "log"
    values: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Rank:
    """A row's prior prominence: base + span * s(column) + the sum of `terms`, clamped to [0, 1].
    The single column is a log Term (or "invert" when invert=True) written inline."""

    base: float = 0.3
    span: float = 0.0
    column: str | None = None
    lo: float = 0.0
    hi: float = 9.0
    invert: bool = False
    terms: tuple[Term, ...] = ()

    def all_terms(self):
        inline = ()
        if self.column is not None:
            scale = "invert" if self.invert else "log"
            inline = (Term(self.column, self.span, self.lo, self.hi, scale),)
        return inline + tuple(self.terms)


@dataclass(frozen=True)
class LayerNames:
    """Which columns of one layer become name index entries. Columns a layer lacks are skipped,
    so a spec can name columns (like `aliases`) that only some builds have."""

    layer: str
    kind: str  # a PlaceKind value
    names: tuple[str, ...] = ("name",)  # official names
    aliases: tuple[str, ...] = ()  # pipe-separated other names; short capitals are abbreviations
    former: tuple[str, ...] = ()  # pipe-separated former names
    codes: tuple[str, ...] = ()  # pipe-separated codes, or templates such as "CA-{code}"
    id_codes: tuple[str, ...] = ()  # id prefixes whose remainder is a code ("iso:" -> "CA-ON")
    strip_suffixes: tuple[str, ...] = ()  # name endings to drop ("Koramangala S.O" -> Koramangala)
    rank: Rank = Rank()
    point: tuple[str, str] | None = None  # label point columns (lat, lon) for polygon layers
    # a layer of mixed kinds: each row's kind is kind_values[row's kind_column value], else `kind`
    kind_column: str | None = None
    kind_values: dict = field(default_factory=dict)


def build(layers, specs):
    """NameData for `layers` (LayerData) from `specs` (LayerNames); layers without a spec are not
    indexed, specs without a layer are ignored."""
    by_name = {layer.name: layer for layer in layers}
    out = {"text": [], "layer": [], "row": [], "kind": [], "rank": [], "name_kind": []}
    points = {}
    for spec in specs:
        layer = by_name.get(spec.layer)
        if layer is None:
            continue
        columns = layer.columns
        rank = rank_of(spec.rank, columns, len(columns["id"]))
        row_kinds = _row_kinds(spec, columns)

        def add(texts, rows, name_kind, spec=spec, rank=rank, row_kinds=row_kinds):
            out["text"] += texts
            out["layer"] += [spec.layer] * len(texts)
            out["row"] += rows
            out["kind"] += [row_kinds[r] for r in rows] if row_kinds else [spec.kind] * len(texts)
            out["rank"] += rank[np.asarray(rows, dtype=np.int64)].tolist()
            out["name_kind"] += name_kind if isinstance(name_kind, list) else [name_kind] * len(texts)

        for column in spec.names:
            if column in columns:
                add(*_values(columns[column], split=False, strip=spec.strip_suffixes), "official")
        for column in spec.aliases:
            if column in columns:
                texts, rows = _values(columns[column])
                kinds = ["abbreviation" if _ABBREVIATION.fullmatch(t) else "alias" for t in texts]
                add(texts, rows, kinds)
        for column in spec.former:
            if column in columns:
                add(*_values(columns[column]), "former")
        for code in spec.codes:
            add(*_codes(code, columns), "code")
        for prefix in spec.id_codes:
            ids = columns["id"]
            rows = [i for i, v in enumerate(ids) if v.startswith(prefix) and len(v) > len(prefix)]
            add([ids[i][len(prefix) :] for i in rows], rows, "code")
        if spec.point and layer.kind == "polygon" and all(c in columns for c in spec.point):
            points[spec.layer] = tuple(_floats(columns[c]) for c in spec.point)
    return NameData(**out, points=points)


def _row_kinds(spec, columns):
    """Each row's PlaceKind value from the spec's kind column, or None when it has none."""
    if spec.kind_column is None or spec.kind_column not in columns:
        return None
    return [spec.kind_values.get(v, spec.kind) for v in columns[spec.kind_column]]


def for_pack(pack, layers):
    """NameData for one of the packs packbuild/name_specs.py describes ("world", "usa", ...)."""
    from .name_specs import SPECS

    if pack not in SPECS:
        raise KeyError(f"no name index spec for pack {pack!r}; known: {', '.join(sorted(SPECS))}")
    return build(layers, SPECS[pack])


def rank_of(rank, columns, n):
    """Each row's rank under `rank` (float64 array)."""
    total = np.full(n, float(rank.base))
    for term in rank.all_terms():
        if term.column not in columns:
            continue
        values = columns[term.column]
        if term.scale == "values":
            s = np.array([term.values.get(v, 0.0) for v in values], dtype=np.float64)
        else:
            v = _floats(values)
            if term.scale == "log":
                v = np.log10(np.maximum(v, 0) + 1)
            s = (v - term.lo) / (term.hi - term.lo)
            if term.scale == "invert":
                s = 1 - s
        total += term.span * np.clip(np.nan_to_num(s, nan=0.0), 0, 1)
    return np.clip(total, 0, 1)


def _values(column, split=True, strip=()):
    """(texts, rows) of a string column's non-empty values, pipe-split unless split=False."""
    texts, rows = [], []
    for i, value in enumerate(column):
        if not value:
            continue
        for text in value.split("|") if split else (value,):
            text = _strip(text.strip(), strip)
            if text:
                texts.append(text)
                rows.append(i)
    return texts, rows


def _strip(text, suffixes):
    for suffix in suffixes:
        if text.endswith(suffix) and len(text) > len(suffix):
            return text[: -len(suffix)].rstrip()
    return text


def _codes(code, columns):
    """(texts, rows) of a code column (pipe-split) or a template filled from each row."""
    names = _TEMPLATE.findall(code)
    if not names:
        if code not in columns:
            return [], []
        texts, rows = _values(columns[code])
        keep = [i for i, t in enumerate(texts) if t not in _NO_CODE]
        return [texts[i] for i in keep], [rows[i] for i in keep]
    if not all(n in columns for n in names):
        return [], []
    texts, rows = [], []
    for i, values in enumerate(zip(*(columns[n] for n in names), strict=True)):
        if all(v is not None and str(v) not in _NO_CODE for v in values):
            texts.append(code.format(**dict(zip(names, map(str, values), strict=True))))
            rows.append(i)
    return texts, rows


def _floats(column):
    """A numeric column as float64, None as NaN."""
    if isinstance(column, np.ndarray) and column.dtype != object:
        return column.astype(np.float64)
    return np.array([math.nan if v is None else float(v) for v in column], dtype=np.float64)
