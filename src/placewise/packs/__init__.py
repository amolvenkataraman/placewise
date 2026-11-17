"""Data packs: write them (`write_pack`, `archive`, `write_index`) and read them (`open_pack`).
`PointIndex` is the layers' nearest-neighbour search, for any set of points.

The on-disk format is docs/pack-format.md (schema 1).
"""

from ._points import PointIndex
from .reader import Layer, Pack, PackFormatError, PackIntegrityError, PointLayer, PolygonLayer, open_pack
from .writer import LayerData, archive, pack_info, write_index, write_pack

__all__ = [
    "Layer",
    "LayerData",
    "Pack",
    "PackFormatError",
    "PackIntegrityError",
    "PointIndex",
    "PointLayer",
    "PolygonLayer",
    "archive",
    "open_pack",
    "pack_info",
    "write_index",
    "write_pack",
]
