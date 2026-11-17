# Pack format, schema 1

A **pack** is a versioned bundle of geographic data that placewise downloads on demand: `world`,
`us`, `ca`, `in`, later `us-nature` and so on. This document is the contract between the code that
builds packs (`build/`), the code that stores them (`placewise.store`) and the code that reads them
(`placewise.packs`). A reader in another language should be implementable from this page alone.

Design goals, in order: **fast to open** (memory-mapped, no parsing at start-up), **small**, **simple**
(numpy's own `.npy` files and JSON, nothing custom where a standard exists), **verifiable**
(every file checksummed) and **attributable** (every layer names its sources).

## On disk

A pack is a directory named `<name>-<version>`, e.g. `world-2026.11/`:

```
world-2026.11/
├─ pack.json                  # manifest (below)
├─ countries/                 # one directory per layer
│  ├─ layer.json
│  ├─ strings.bin  strings.idx.npy
│  ├─ geom/...                # polygon layers only
│  ├─ grid/...                # polygon layers only
│  └─ col/<field>.npy         # one file per property column
└─ cities/ ...
```

Every array is a standard `.npy` file (NumPy format 1.0 or 2.0), little-endian, C order, so it can
be opened with `numpy.load(path, mmap_mode="r")` and costs nothing until touched.

## pack.json

```json
{
  "schema": 1,
  "name": "world",
  "version": "2026.11",
  "created": "2026-11-17T00:00:00Z",
  "layers": ["countries", "admin1", "cities", "airports"],
  "sources": ["naturalearth", "geonames", "ourairports"],
  "files": {"countries/layer.json": {"sha256": "…", "size": 1234}, "…": {}}
}
```

- `schema`: this document's version. A reader refuses packs whose schema it doesn't know.
- `name`: `[a-z0-9][a-z0-9_-]*` (it becomes a directory name; layer names follow the same rule,
  field names `[A-Za-z_][A-Za-z0-9_]*`).
- `version`: CalVer `YYYY.MM` with MM 01–12, optionally `.N` (N ≥ 1, no leading zero) for
  re-releases in the same month.
- `sources`: attribution source ids (`placewise.constants.licences`); each must also appear in a
  layer's `sources`.
- `files`: every other file in the pack, keyed by its POSIX path relative to the pack directory,
  with its SHA-256 and size; the store verifies them after
  download and `placewise verify` re-checks them.

## layer.json

```json
{
  "name": "countries",
  "kind": "polygon",
  "count": 258,
  "sources": ["naturalearth"],
  "fields": {
    "id":   {"type": "str"},
    "name": {"type": "str"},
    "iso2": {"type": "str"},
    "population": {"type": "i8"},
    "tier": {"type": "i1", "null": -1}
  },
  "coords": "e7"
}
```

- `kind` is `point` or `polygon` (`line` arrives with the line engine in a later schema).
- `count` is the number of features `n`. Every column has exactly `n` rows.
- Every layer has `id` and `name` string fields. `id` is stable across releases
  (`"geonames:6167865"`, `"wikidata:Q16"`, `"iso:CA"`).
- Field types: `str`, `i1 i2 i4 i8`, `u1 u2 u4`, `f4 f8`, `bool`. Integer fields may name a `null`
  sentinel; float nulls are NaN; a `str` null is the empty string.
- `coords` is `e7` (int32 degrees × 10⁷, ~1 cm, as in Google location history exports) for every coordinate array,
  rounded half to even.

## Columns

- Numeric field `f`: `col/f.npy`, shape `(n,)`, dtype from `type`.
- String field `f`: `col/f.npy` is `int32` indexes into the layer's **string table**.
- String table: `strings.bin` is all distinct strings of the layer, UTF-8, concatenated;
  `strings.idx.npy` (int64, length `m + 1`) holds byte offsets, so string `k` is
  `strings.bin[idx[k]:idx[k+1]]`. Index 0 is always the empty string. Strings are deduplicated, and one table
  serves every `str` column of the layer. Ids are never empty.

## Point layers

`geom/lat.npy` and `geom/lon.npy`: int32 e7, shape `(n,)`. Points may carry a `radius_m` (f4)
column for things known by a centre and a size.

## Polygon layers

Each feature is one or more polygons; each polygon is an outer ring plus holes. Coordinates are
flattened, with offset arrays in the style of GeoArrow:

| File | dtype | Shape | Meaning |
|---|---|---|---|
| `geom/lat.npy`, `geom/lon.npy` | int32 e7 | `(v,)` | all vertices of all rings; rings are closed implicitly (first vertex not repeated) |
| `geom/ring.npy` | int64 | `(r + 1,)` | vertex offset of each ring |
| `geom/part.npy` | int64 | `(p + 1,)` | ring offset of each polygon (first ring is the outer one) |
| `geom/feature.npy` | int64 | `(n + 1,)` | polygon offset of each feature |
| `geom/bbox.npy` | int32 e7 | `(n, 4)` | south, west, north, east per feature; west > east crosses the antimeridian |

Point-in-polygon uses the even-odd rule across all rings of a feature, so ring orientation doesn't
matter to readers (builders still write outer rings counter-clockwise, holes clockwise, as GeoJSON
does). Containment is planar in (lat, lon) degrees. Features crossing the antimeridian are split at
±180 (RFC 7946 §3.1.9); an edge may span more than 180° of longitude only along a parallel from +180
to −180. A feature's bbox west/east is the shortest longitude range covering all its parts.

### Grid index

A regular grid of `cell_deg` degrees answers "which features might contain this point" without
looking at geometry. `items` lists, ascending, every feature that may contain a point of the cell:
at least those whose boundary touches the cell or that cover it (builders may also include features
whose bbox merely touches it). `inside[c]` is f when f wholly covers cell c (its four corners are
inside f and no edge of f touches the closed cell, so a cell in a hole is not covered) and every
earlier candidate misses c entirely; otherwise −1. It gives the first-match answer and must not be
used for `query_all`.

| File | dtype | Shape | Meaning |
|---|---|---|---|
| `grid/meta.json` | — | — | `{"cell_deg": 1.0, "rows": 180, "cols": 360}`: rows = ceil(180 / cell_deg), cols = ceil(360 / cell_deg); row 0 starts at −90°, col 0 at −180° |
| `grid/cell.npy` | int64 | `(rows * cols + 1,)` | offsets into `items` per cell |
| `grid/items.npy` | int32 | `(k,)` | candidate feature indexes, ascending within each cell |
| `grid/inside.npy` | int32 | `(rows * cols,)` | feature that wholly covers the cell, or −1 |

A point's row is floor((lat + 90) / cell_deg) clamped to [0, rows − 1], likewise for columns, so a
point on a cell edge belongs to the cell to its north-east and lat 90 / lon 180 fall in the last row
or column (180 is not wrapped to −180). Features earlier in the layer win
when several contain a point; builders order features so the most specific comes first when that
matters.

## Distribution

A release publishes, per pack, `<name>-<version>.tar.xz` (the directory, compressed with the
standard library's `tarfile`/`lzma`) and one `index.json` for all packs:

```json
{
  "schema": 1,
  "packs": {
    "world": {"version": "2026.11", "schema": 1, "url": "world-2026.11.tar.xz",
              "sha256": "…", "size_bytes": 123, "sources": ["naturalearth", "geonames"]}
  }
}
```

Relative `url`s resolve against the index's own URL, so a mirror is a copy of the directory. Each
entry is `PackInfo.to_dict()` minus `name` (it's the key), plus `url`. The archive holds one
top-level directory `<name>-<version>/` with only regular files and directories. The store downloads to a temporary file, checks the archive's
SHA-256, unpacks to a temporary directory (refusing absolute paths, `..` and links), checks every
file in `pack.json`, then renames the directory into place, so a pack is either fully there or
not there at all. Older versions stay until `placewise data prune`.

## Compatibility

- Adding a layer, a field or a file is not a schema change: readers ignore what they don't know.
- Changing the meaning or layout of anything above is: bump `schema`.
