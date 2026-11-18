"""Data packs: write them (`write_pack`, `archive`, `write_index`) and read them (`open_pack`).
`PointIndex` is the layers' nearest-neighbour search, for any set of points. `Pack.names` is
the name index (`NameIndex`) forward search reads; `NameData` is what write_pack builds it from.

The on-disk format is docs/pack-format.md (schema 1).
"""

from ._names import Candidates, NameIndex, Resolved
from ._names_write import NameData
from ._points import PointIndex
from .reader import Layer, Pack, PackFormatError, PackIntegrityError, PointLayer, PolygonLayer, open_pack
from .writer import LayerData, archive, pack_info, write_index, write_pack

__all__ = [
    "Candidates",
    "Layer",
    "LayerData",
    "NameData",
    "NameIndex",
    "Pack",
    "PackFormatError",
    "PackIntegrityError",
    "PointIndex",
    "PointLayer",
    "PolygonLayer",
    "Resolved",
    "archive",
    "open_pack",
    "pack_info",
    "write_index",
    "write_pack",
]
