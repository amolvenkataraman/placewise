"""What a pack covers: its kind (base, country, parks, water, notable, postal), the countries it
serves (ISO 3166-1 alpha-2, or "*" for world-wide), the packs it needs beside it and its size once
installed. Releases write these into index.json (packbuild/release.py); for an index or pack.json
that predates them, the pack's name and layers say the same (docs/pack-format.md, "Index")."""

from dataclasses import dataclass

from placewise.constants import store as const
from placewise.constants.packs import SHARE_ALIKE_SUFFIX
from placewise.constants.parks import POLYGON_PREFIX

_WORLD = "world"


@dataclass(frozen=True, slots=True)
class Coverage:
    kind: str
    covers: tuple[str, ...] = ()  # alpha-2 codes, ("*",) world-wide, () unknown
    requires: tuple[str, ...] = ()  # pack names installed with this one
    installed_bytes: int | None = None  # on disk once unpacked; None when the index doesn't say

    @property
    def worldwide(self):
        return const.COVERS_WORLD in self.covers

    def serves(self, countries):
        """Whether the pack has data for any of `countries` (alpha-2 codes)."""
        return self.worldwide or not set(self.covers).isdisjoint(countries)

    def to_entry(self):
        """The index.json fields."""
        entry = {"kind": self.kind, "covers": list(self.covers), "requires": list(self.requires)}
        if self.installed_bytes is not None:
            entry["installed_bytes"] = self.installed_bytes
        return entry


def derive(name, manifest=None, *, manifest_bytes=0):
    """The Coverage of pack `name`: fields pack.json (`manifest`, a dict) carries win, the rest
    comes from the name ("usa-zip": postal, US, requires usa) and the layers. With a manifest, the
    installed size is its files' sizes plus `manifest_bytes` (pack.json itself)."""
    manifest = manifest or {}
    base = name[: -len(SHARE_ALIKE_SUFFIX)] if name.endswith(SHARE_ALIKE_SUFFIX) else name
    head, _, suffix = base.partition("-")
    country = _alpha2(head)
    if base == _WORLD:
        kind, covers = const.KIND_BASE, (const.COVERS_WORLD,)
    elif country and not suffix:
        kind, covers = const.KIND_COUNTRY, (country,)
    else:
        covers = (const.COVERS_WORLD,) if head == _WORLD else (country,) if country else ()
        kind = _suffix_kind(suffix) or _layer_kind(manifest.get("layers", ())) or const.KIND_OTHER
    requires = (head,) if kind == const.KIND_POSTAL and country else ()
    installed = None
    if isinstance(manifest.get("files"), dict):
        installed = manifest_bytes + sum(int(f.get("size", 0)) for f in manifest["files"].values())
    return Coverage(
        kind=_text(manifest, "kind") or kind,
        covers=_codes(manifest, "covers", covers),
        requires=_names(manifest, "requires", requires),
        installed_bytes=installed,
    )


def from_entry(name, entry):
    """The Coverage an index entry gives, falling back to the name for fields it lacks. A field
    of the wrong type is a ValueError naming it."""
    derived = derive(name)
    installed = entry.get("installed_bytes")
    if installed is not None and (
        not isinstance(installed, int) or isinstance(installed, bool) or installed < 0
    ):
        raise ValueError("installed_bytes must be a whole number of bytes")
    return Coverage(
        kind=_text(entry, "kind") or derived.kind,
        covers=_codes(entry, "covers", derived.covers),
        requires=_names(entry, "requires", derived.requires),
        installed_bytes=installed,
    )


def _alpha2(code):
    """The alpha-2 code for a country pack's name (alpha-3 "usa", or the older alpha-2 "us")."""
    from placewise.constants.countries import BY_ALPHA2, BY_ALPHA3

    upper = code.upper()
    if len(code) == 3 and upper in BY_ALPHA3:
        return BY_ALPHA3[upper].alpha2
    if len(code) == 2 and upper in BY_ALPHA2:
        return upper
    return None


def _suffix_kind(suffix):
    return const.SUFFIX_KINDS.get(suffix) or const.SUFFIX_KINDS.get(suffix.partition("-")[0])


def _layer_kind(layers):
    for layer in layers:
        if layer.startswith(POLYGON_PREFIX + "_"):
            return const.LAYER_KINDS[POLYGON_PREFIX]
        if layer in const.LAYER_KINDS:
            return const.LAYER_KINDS[layer]
    return None


def _text(doc, key):
    value = doc.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _strings(doc, key):
    value = doc.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise ValueError(f"{key} must be a list of strings")
    return value


def _codes(doc, key, default):
    value = _strings(doc, key)
    return default if value is None else tuple(sorted(set(value)))


def _names(doc, key, default):
    value = _strings(doc, key)
    return default if value is None else tuple(dict.fromkeys(value))
