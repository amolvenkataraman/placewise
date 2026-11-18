"""Wikidata (CC0) notable places from the kinds' cached query results (QLever TSV exports).

A TSV export has a header of `?variable` names, then one row per item; each value is in N-Triples
form (`<iri>`, `"text"@en`, `"text"`, a bare number or `POINT(lon lat)`), empty when unbound.
`read` merges every kind's rows into one record per item: the first kind in kinds.KINDS order,
aliases and ids from every row.
"""

import re
import time
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path

from ...fetch import fetch as fetch_file
from ...fetch import metadata
from .. import url
from . import kinds

SOURCE = "wikidata"
RETRIES = 3
RETRY_WAIT_S = 20.0
_ITEM = re.compile(r"^<http://www\.wikidata\.org/entity/(Q\d+)>$")
_POINT = re.compile(r"^POINT\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)$", re.IGNORECASE)
_LITERAL = re.compile(r'^"(.*)"(?:@[A-Za-z0-9-]+|\^\^<[^>]*>)?$', re.DOTALL)
_ESCAPE = re.compile(r'\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|[tbnrf"\'\\])')
_SIMPLE = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", '"': '"', "'": "'", "\\": "\\"}


@dataclass
class Item:
    qid: str
    name: str
    lat: float
    lon: float
    kind: str
    sitelinks: int
    countries: set = field(default_factory=set)
    aliases: list = field(default_factory=list)
    codes: dict = field(default_factory=dict)


def fetch(cache_dir, refresh=False):
    """{kind name: cached TSV}; each query gets its own folder (every URL's path is /api/wikidata).
    A cached result of another query (the kind's classes changed) is fetched again."""
    out = {}
    for kind in kinds.KINDS:
        folder = Path(cache_dir) / f"notable-{kind.name.replace('_', '-')}"
        query_url = url(SOURCE, kinds.download_name(kind))
        stale = _cached_url(folder / "wikidata") not in (None, query_url)
        out[kind.name] = _fetch_retrying(query_url, folder, refresh or stale)
    return out


def _fetch_retrying(query_url, folder, refresh, attempts=RETRIES, wait_s=RETRY_WAIT_S):
    """fetch_file, tried again after a server error (QLever answers 500 now and then)."""
    for attempt in range(attempts):
        try:
            return fetch_file(query_url, folder, refresh=refresh, timeout=900)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == attempts - 1:
                raise
            time.sleep(wait_s * (attempt + 1))
    raise AssertionError("unreachable")


def _cached_url(path):
    """The URL a cached file was fetched from, or None when it isn't cached."""
    try:
        return metadata(path)["url"]
    except (FileNotFoundError, KeyError, ValueError):
        return None


def value(text):
    """One TSV cell as a plain string: literal text unescaped, IRIs and numbers as written."""
    m = _LITERAL.match(text)
    if not m:
        return text
    return _ESCAPE.sub(_unescape, m[1])


def _unescape(m):
    s = m[1]
    return chr(int(s[1:], 16)) if s[0] in "uU" else _SIMPLE[s]


def rows(path):
    """{variable: plain value} per row of a TSV export ("" where unbound)."""
    with Path(path).open(encoding="utf-8") as f:
        header = [h.lstrip("?") for h in f.readline().rstrip("\n").split("\t")]
        for line in f:
            cells = line.rstrip("\n").split("\t")
            if len(cells) != len(header):
                raise ValueError(f"{path}: a row has {len(cells)} cells, the header {len(header)}")
            yield {h: value(c) if c else "" for h, c in zip(header, cells, strict=True)}


def kind_items(kind, path):
    """Items of one kind's export: rows with a Wikidata item, a label other than its id and an
    Earth coordinate."""
    variables = kinds.code_variables(kind)
    for row in rows(path):
        m = _ITEM.match(row["item"])
        point = _POINT.match(row["point"])
        label = " ".join(row["label"].split())
        if not m or not point or not label or label == m[1]:
            continue
        lon, lat = float(point[1]), float(point[2])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            continue
        codes = {}
        for variable, _ in variables:  # columns listing several properties take the first found
            column = variable.rstrip("0123456789")
            if row.get(variable) and column not in codes:
                codes[column] = row[variable].strip().upper()  # Amtrak writes "was"
        countries = {c.strip().upper() for c in row["countries"].split("|") if c.strip()}
        aliases = [a for a in row["aliases"].split("|") if a.strip()]
        yield Item(m[1], label, lat, lon, kind.name, int(row["sitelinks"] or 0), countries, aliases, codes)


def read(paths):
    """{qid: Item} from {kind name: export path}: an item listed by several kinds takes the first in
    kinds.KINDS order and gathers every row's aliases, countries and ids."""
    found = {}
    for kind in sorted((kinds.BY_NAME[name] for name in paths), key=lambda k: kinds.PRIORITY[k.name]):
        for item in kind_items(kind, paths[kind.name]):
            known = found.get(item.qid)
            if known is None:
                found[item.qid] = item
                continue
            known.countries |= item.countries
            known.aliases += [a for a in item.aliases if a not in known.aliases]
            for column, code in item.codes.items():
                known.codes.setdefault(column, code)
    return found
