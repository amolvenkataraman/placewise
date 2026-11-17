"""Wikidata (CC0): driving side per ISO 3166-1 alpha-2 code, from a cached SPARQL query result.

The query (the registry's `wikidata` / `driving_side` download) returns rows of `iso` (P297) and
`side` (an item URI, P1622), leaving out deprecated statements and ones with an end time.
"""

import json
from pathlib import Path

SIDES = {"Q11920728": "left", "Q14565199": "right"}


def driving_sides(path):
    """{alpha2: "left" | "right"}; a code whose statements disagree, or name another value, is left out."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))["results"]["bindings"]
    found = {}
    for row in rows:
        code = row["iso"]["value"].strip().upper()
        side = SIDES.get(row["side"]["value"].rsplit("/", 1)[-1])
        found.setdefault(code, set()).add(side)
    return {code: sides.pop() for code, sides in found.items() if len(sides) == 1 and None not in sides}
