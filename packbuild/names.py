"""The name index every pack carries (docs/pack-format.md, "Name index"), built from the pack's
own layers by a small spec per layer: which columns hold names, pipe-separated aliases and exact
codes, what kind of place a row is and how prominent (rank). Every pack builder ends with

    write_pack(out_dir, name, version, layers, names=names.for_pack("world", layers))

The specs per pack are in packbuild/name_specs.py.
"""

from dataclasses import dataclass

from placewise.packs import NameData


@dataclass(frozen=True)
class Rank:
    """A row's prior prominence in [0, 1]: base + span * s, where s maps log10(column + 1) from
    [lo, hi] onto [0, 1] (clamped; nulls give 0). `invert` reads small values as prominent (a
    scalerank or tier): s = 1 - (value - lo) / (hi - lo), linear."""

    base: float = 0.3
    span: float = 0.0
    column: str | None = None
    lo: float = 0.0
    hi: float = 9.0
    invert: bool = False


@dataclass(frozen=True)
class LayerNames:
    """Which columns of one layer become name index entries. Columns a layer lacks are skipped,
    so a spec can name columns (like `aliases`) that only some builds have."""

    layer: str
    kind: str  # a PlaceKind value
    names: tuple[str, ...] = ("name",)  # official names
    aliases: tuple[str, ...] = ()  # pipe-separated other names
    abbreviations: tuple[str, ...] = ()  # short forms: "GTA", "NCR"
    codes: tuple[str, ...] = ("id",)  # matched exactly only: ids, ISO, IATA, postal codes
    rank: Rank = Rank()
    point: tuple[str, str] | None = None  # label point columns (lat, lon) for polygon layers


def build(layers, specs):
    """NameData for `layers` (LayerData) from `specs` (LayerNames); layers without a spec are not
    indexed."""
    raise NotImplementedError(NameData)


def for_pack(pack, layers):
    """NameData for one of the packs packbuild/name_specs.py describes ("world", "usa", ...)."""
    raise NotImplementedError
