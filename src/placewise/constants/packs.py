"""Pack format, schema 1 (docs/pack-format.md): names, numbers and limits shared by writer and reader."""

SCHEMA = 1  # the pack format version this code reads and writes
E7 = 10_000_000  # coordinates are stored as int32 degrees x 10^7 (~1 cm)
COORDS = "e7"
DEFAULT_CELL_DEG = 1.0  # polygon grid cell; ~64 800 cells covers the world in ~0.5 MB of offsets

KINDS = ("point", "polygon")
FIELD_TYPES = ("str", "i1", "i2", "i4", "i8", "u1", "u2", "u4", "f4", "f8", "bool")
INT_TYPES = ("i1", "i2", "i4", "i8", "u1", "u2", "u4")
REQUIRED_FIELDS = ("id", "name")

# CalVer: YYYY.MM, plus .N (N >= 1) for re-releases in the same month
VERSION_PATTERN = r"\d{4}\.(0[1-9]|1[0-2])(\.[1-9]\d*)?"
# names become directory and file names, so they stay portable and can't climb out of the pack
NAME_PATTERN = r"[a-z0-9][a-z0-9_-]*"
FIELD_PATTERN = r"[A-Za-z_][A-Za-z0-9_]*"

PACK_JSON = "pack.json"
INDEX_JSON = "index.json"
LAYER_JSON = "layer.json"
STRINGS_BIN = "strings.bin"
STRINGS_IDX = "strings.idx.npy"
COL_DIR = "col"
GEOM_DIR = "geom"
GRID_DIR = "grid"
GRID_META = "meta.json"
ARCHIVE_SUFFIX = ".tar.xz"
# share-alike data (constants.licences.SHARE_ALIKE) ships only in packs named <name>-sa
SHARE_ALIKE_SUFFIX = "-sa"

# in-memory point grid for nearest(): cell sizes that divide 180 so columns wrap cleanly at the
# antimeridian, and the mean number of points per occupied cell to aim for when picking one
POINT_CELL_DEGS = (0.05, 0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0, 15.0, 30.0, 45.0, 90.0)
POINT_CELL_TARGET = 16

HASH_CHUNK = 1 << 20  # bytes read at a time when checksumming

# polygon queries refine each feature's boundary cells in memory to cells of about this size, so
# only points within a fine cell of an edge pay for the exact test
REFINE_CELL_DEG = 0.125
# ...once a feature has been tested this many points in all; single lookups never pay to build it
REFINE_AFTER_POINTS = 256
