# Pack format, schema 1

A **pack** is a versioned bundle of geographic data that placewise downloads on demand: `world`,
`usa`, `can`, `ind`, later `usa-nature` and so on (a country pack is named by the country's
lower-case ISO 3166-1 alpha-3 code). This document is the contract between the code that
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
  field names `[A-Za-z_][A-Za-z0-9_]*`). A country pack is named by the country's lower-case
  ISO 3166-1 alpha-3 code; a pack carrying share-alike sources (ODbL, CC BY-SA) ends in `-sa`, and
  no other pack may carry them (checked at release).
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
| `grid/meta.json` | — | — | `{"cell_deg": 0.25, "rows": 230, "cols": 470, "row0": 430, "col0": 140}`: the rectangle of cells stored (below) |
| `grid/cell.npy` | int64 | `(rows * cols + 1,)` | offsets into `items` per cell |
| `grid/items.npy` | int32 | `(k,)` | candidate feature indexes, ascending within each cell |
| `grid/inside.npy` | int32 | `(rows * cols,)` | feature that wholly covers the cell, or −1 |

The cells are those of the **world grid** of `cell_deg`: R = ceil(180 / cell_deg) rows from −90°
and C = ceil(360 / cell_deg) columns from −180°. A point's world row is floor((lat + 90) /
cell_deg) clamped to [0, R − 1], likewise its column in [0, C − 1], so a point on a cell edge
belongs to the cell to its north-east and lat 90 / lon 180 fall in the last row or column (180 is
not wrapped to −180).

A grid stores only the rectangle of world cells that hold a candidate: `rows` rows from world row
`row0` and `cols` columns from world column `col0`, going east and wrapping past the antimeridian
(column `(col0 + j) mod C`), so a layer of one country doesn't pay for the whole world's empty
cells (a 0.25° world grid is 12 MB). Stored cell k = r × cols + j is world row `row0 + r`, world
column `(col0 + j) mod C`. A point lies on the grid when 0 ≤ world row − row0 < rows and (world
column − col0) mod C < cols; a point off the grid has no candidates, and lies in no feature. A
layer with no features has `rows` = `cols` = 0. Builders cut the grid to the narrowest such
rectangle (columns: leaving out the widest run of empty columns round the world); a world-wide
layer keeps the whole world (`row0` = `col0` = 0).

Packs written before grids were cut (2026-11) have no `row0` / `col0` and `rows` = R, `cols` =
C; readers take `row0` = `col0` = 0 when they're absent, which is the same grid. A reader that
ignores `row0` / `col0` misreads a cut grid, so they're required reading from now on.

Features earlier in the layer win when several contain a point; builders order features so the
most specific comes first when that matters.

## Name index

A pack may carry a **name index** for forward search (name in, place out) in the reserved
directory `names/` (no layer may be called `names`; it is not listed in `pack.json`'s `layers`,
but its files are in `files` like every other). Readers that don't know it ignore it. It is built
from the pack's own layers (`packbuild/names.py`, specs per pack in `packbuild/name_specs.py`).

```
names/
├─ names.json
├─ name_keys.bin  name_keys.idx.npy  name_start.npy    # names, aliases, abbreviations
├─ code_keys.bin  code_keys.idx.npy  code_start.npy    # codes: matched exactly only
├─ layer.npy  row.npy  kind.npy  rank.npy  name_kind.npy   # one row per entry
├─ entry/<layer>.npy   ids/<layer>.npy                 # per indexed layer
├─ inside/<layer>.npy  radius/<layer>.npy              # per indexed polygon layer
└─ trigram_codes.npy  trigram_start.npy  trigram_counts.npy  trigram_repeats.npy
   trigram_postings.bin                                # fuzzy matching (optional)
```

`names.json`: `{"format": 1, "layers": [...], "kinds": [...], "name_kinds": [...], "entries": E,
"names": Kn, "codes": Kc}`. `layers` are the indexed layers (an entry's `layer` indexes it),
`kinds` the place kinds (`PlaceKind` values) an entry's `kind` indexes, `name_kinds` = official,
alias, former, abbreviation, code (an entry's `name_kind` indexes it).

**Entries** are one per (normalised text, feature): `layer` (u1, or u2 past 256 layers), `row`
(i4), `kind` (u1), `rank` (f4, the feature's prior prominence in [0, 1]: population, area, tier,
fame) and `name_kind` (u1). Name entries come first, sorted by key, then rank descending, then
layer and row; code entries follow, sorted the same way. A (text, feature) pair appears once,
with its most official name kind.

**Keys.** Names are normalised with `placewise.constants._keys.city_key` (lower case, accents and
dots dropped, `&` as "and", hyphens and space runs as one space, St/Ft/Mt spelled out), codes with
`key` (the same without the St/Ft/Mt expansion). Each table (`name_`, `code_`) holds its distinct
keys in ascending UTF-8 byte order (= code point order): `*_keys.bin` is their UTF-8 bytes
concatenated, `*_keys.idx.npy` (int32, K + 1) their byte offsets, and `*_start.npy` (int32,
K + 1) each key's entry range: key k's entries are `start[k]:start[k + 1]`. Exact lookup is a
binary search; prefix lookup is the range from the prefix to the prefix followed by byte 0xFF.

**Ids.** Every row of every indexed layer can be found by its `id`: `ids/<layer>.npy` (int32,
the layer's count) lists the layer's rows in ascending id order (code point order), and
`entry/<layer>.npy` (int32, the layer's count) gives each row's most official entry (−1 when it
has none), whose kind and rank an id match reports.

**Inside points.** `inside/<layer>.npy` (int32 e7, shape (n, 2): lat, lon) is a point inside
each feature of an indexed polygon layer (the layer's label point when the builder gave one and
it is inside, else the middle of the widest inside stretch of a few parallels across the
feature's largest polygon), checked with the even-odd test after rounding; `radius/<layer>.npy`
(f4, km) is the distance from it to the feature's farthest vertex. Point layers need neither:
their point is the feature, and their radius comes from a `radius_km` or `radius_m` column, else
a disc of 2,000 people per km² for a `population` column (0.5 to 40 km), else 1 km.

**Fuzzy matching** reads padded character trigram postings over the name keys: each key (as
code points, with one space added before and after) holds the trigrams starting at each of its
characters, " to", "tor" ... "to " for "toronto", and a trigram's posting lists the name keys
(numbers into `name_keys`, ascending) holding it. A trigram's code is its three code points, 21
bits each, the first highest (`(a << 42) | (b << 21) | c`).

- `trigram_codes.npy` (u8, T): the distinct trigram codes, ascending.
- `trigram_counts.npy` (i4, T): how many keys each trigram's posting lists.
- `trigram_start.npy` (u4, T + 1; i8 should the postings pass 4 GiB): each posting's byte range
  in `trigram_postings.bin`: trigram t's is `start[t]:start[t + 1]`.
- `trigram_postings.bin`: every posting, in trigram order, as its first key number and then the
  differences between consecutive key numbers, each a varint (7 bits per byte, low bits first,
  the high bit set on every byte but a number's last).
- `trigram_repeats.npy` (i4, shape (r, 2): key, distinct trigrams): the keys holding a trigram
  more than once ("banana"); every other key holds as many distinct trigrams as it has characters.

The postings add about a third to the name index (all of it for very small packs). The files are
optional: readers build the same postings in memory on the first fuzzy lookup when a pack written
before them lacks them (a few hundred ms per pack of a couple of hundred thousand keys).

## Distribution

A release publishes, per pack, `<name>-<version>.tar.xz` (the directory, compressed with the
standard library's `tarfile`/`lzma`; LZMA2 preset 9 with lc=0, lp=2, pb=2, which suits the int32
arrays and any xz decoder reads) and one `index.json` for all packs:

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
