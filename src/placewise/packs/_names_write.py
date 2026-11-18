"""Write a pack's name index (docs/pack-format.md, "Name index") from `NameData`."""

from collections.abc import Sequence
from dataclasses import dataclass, field


@dataclass
class NameData:
    """Names to index, for write_pack(..., names=NameData(...)): one row per (text, feature).

    text       the name or code as written; the writer normalises it (city_key for names, key for
               codes), so every reader lookup compares like with like
    layer      the layer name of the feature
    row        the feature's row in that layer
    kind       a PlaceKind value ("locality", "park" ...)
    rank       prior prominence in [0, 1], higher first
    name_kind  one of placewise.constants.names.NAME_KINDS ("official", "alias", "code" ...);
               "code" entries are matched exactly by NameIndex.codes, the rest by name
    points     optional label points per polygon layer, {layer: (lat, lon)} arrays of the layer's
               length (NaN where none): used as the feature's inside point when they are inside it
    """

    text: Sequence[str]
    layer: Sequence[str]
    row: Sequence[int]
    kind: Sequence[str]
    rank: Sequence[float]
    name_kind: Sequence[str]
    points: dict = field(default_factory=dict)

    @classmethod
    def from_rows(cls, rows, points=None):
        """From (text, layer, row, kind, rank, name_kind) tuples: the small-index builder for tests."""
        rows = list(rows)
        columns = list(zip(*rows, strict=True)) if rows else [()] * 6
        return cls(*columns, points=dict(points or {}))

    def __len__(self):
        return len(self.text)
