"""Open packs (docs/pack-format.md) and answer questions from them.

Opening reads only the JSON manifests; every array is memory-mapped on first use, so a pack costs
next to nothing until it is queried, and then only for the layers and columns touched. The layers
are `Layer` and `PointLayer` (_layer.py) and `PolygonLayer` (_polygon_layer.py).

Polygon geometry is planar in (lat, lon), with the even-odd rule over all rings of a feature, as in
placewise.geo.shapes. A point exactly on an edge may be reported inside or outside, and the answer
may differ between neighbouring points on the same edge; don't rely on either.
"""

import hashlib
from pathlib import Path, PurePosixPath

from placewise.constants import names as names_consts
from placewise.constants import packs as consts

from ._layer import Layer, PackFormatError, PointLayer, read_json
from ._lazy import once
from ._names.index import NameIndex
from ._polygon_layer import PolygonLayer


class PackIntegrityError(ValueError):
    """A file is missing or doesn't match the checksum or size pack.json records for it."""


def open_pack(path, verify=False):
    """Open the pack directory at `path`. verify=True re-hashes every file first (slow for big
    packs; the store already verified them once after download)."""
    path = Path(path)
    manifest = read_json(path / consts.PACK_JSON, consts.PACK_JSON)
    schema = manifest.get("schema")
    if schema not in consts.READABLE_SCHEMAS:
        raise PackFormatError(
            f"{path}: pack schema {schema} is not supported; this placewise reads schemas "
            f"{sorted(consts.READABLE_SCHEMAS)} "
            "(update placewise, or download a pack built for it)"
        )
    for key in ("name", "version", "layers", "files"):
        if key not in manifest:
            raise PackFormatError(f"{path / consts.PACK_JSON}: missing {key!r}")
    layers = {}
    for name in manifest["layers"]:
        meta = read_json(path / name / consts.LAYER_JSON, f"{name}/{consts.LAYER_JSON}")
        cls = {"point": PointLayer, "polygon": PolygonLayer}.get(meta.get("kind"), Layer)
        layers[name] = cls(path / name, meta)
    pack = Pack(path, manifest, layers)
    if verify:
        pack.verify()
    return pack


class Pack:
    def __init__(self, path, manifest, layers):
        self.path = Path(path)
        self.manifest = manifest
        self.name = manifest["name"]
        self.version = manifest["version"]
        self.schema = manifest["schema"]
        self.created = manifest.get("created")
        self.sources = tuple(manifest.get("sources", ()))
        self.files = manifest["files"]
        self.layers = layers

    def __getitem__(self, name):
        try:
            return self.layers[name]
        except KeyError:
            raise KeyError(
                f"pack {self.name!r} has no layer {name!r}; it has {', '.join(self.layers)}"
            ) from None

    def __contains__(self, name):
        return name in self.layers

    @once
    def names(self):
        """The pack's name index (a NameIndex for forward search), or None when it has none."""
        if not (self.path / names_consts.NAMES_DIR / names_consts.NAMES_JSON).is_file():
            return None
        return NameIndex(self.path / names_consts.NAMES_DIR, self)

    def __iter__(self):
        return iter(self.layers.values())

    def __repr__(self):
        return f"<Pack {self.name}-{self.version}: {', '.join(self.layers)}>"

    def verify(self):
        """Re-hash every file pack.json lists; raise PackIntegrityError naming the first bad one."""
        root = self.path.resolve()
        for rel, meta in self.files.items():
            pure = PurePosixPath(rel)
            if pure.is_absolute() or ".." in pure.parts or not pure.parts:
                raise PackIntegrityError(f"{rel}: path escapes the pack")
            target = root.joinpath(*pure.parts)
            if not target.is_file():
                raise PackIntegrityError(f"{rel}: missing")
            size = target.stat().st_size
            if size != meta.get("size"):
                raise PackIntegrityError(f"{rel}: size {size}, expected {meta.get('size')}")
            digest = hashlib.sha256()
            with target.open("rb") as fh:
                while chunk := fh.read(consts.HASH_CHUNK):
                    digest.update(chunk)
            if digest.hexdigest() != meta.get("sha256"):
                raise PackIntegrityError(f"{rel}: sha256 mismatch (corrupt or modified)")
