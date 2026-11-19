"""A minimal GeoTIFF reader: one band of integers or floats, read a band of rows at a time.

Enough for the GHSL grids as JRC publishes them (BigTIFF, 256 x 256 tiles, LZW with horizontal
differencing) and for plain TIFFs: classic or BigTIFF, either byte order, strips or tiles,
uncompressed, LZW (packbuild.sources.ghsl.lzw) or Deflate (zlib), predictor 1 or 2. The
georeference is the pixel scale and tie point (an axis-aligned grid); anything else (several
bands, planar configurations, rotation, JPEG, floating-point predictor) is refused rather than
misread.
"""

import struct
import zlib
from dataclasses import dataclass

import numpy as np

from . import lzw

# baseline and GeoTIFF tags read here (TIFF 6.0; GeoTIFF 1.1)
WIDTH, HEIGHT, BITS, COMPRESSION, PHOTOMETRIC = 256, 257, 258, 259, 262
STRIP_OFFSETS, SAMPLES, ROWS_PER_STRIP, STRIP_BYTES = 273, 277, 278, 279
PLANAR, PREDICTOR = 284, 317
TILE_WIDTH, TILE_HEIGHT, TILE_OFFSETS, TILE_BYTES = 322, 323, 324, 325
SAMPLE_FORMAT = 339
PIXEL_SCALE, TIE_POINT, GEO_ASCII, NODATA = 33550, 33922, 34737, 42113

NONE, LZW, DEFLATE, DEFLATE_OLD = 1, 5, 8, 32946
_TYPES = {  # TIFF field type -> (struct code, size)
    1: ("B", 1), 2: ("s", 1), 3: ("H", 2), 4: ("I", 4), 5: ("II", 8), 6: ("b", 1), 7: ("B", 1),
    8: ("h", 2), 9: ("i", 4), 10: ("ii", 8), 11: ("f", 4), 12: ("d", 8), 16: ("Q", 8), 17: ("q", 8),
}  # fmt: skip
_KINDS = {1: "u", 2: "i", 3: "f"}  # SampleFormat -> numpy kind
_SAME_TILE_BYTES = 4096  # compressed tiles at most this big are decoded once per distinct content


@dataclass(frozen=True)
class Grid:
    """Where pixel (row, col) lies: its top-left corner is (x0 + col * dx, y0 - row * dy)."""

    x0: float
    y0: float
    dx: float
    dy: float


class GeoTiff:
    """One single-band GeoTIFF held in memory (`data`: the file's bytes)."""

    def __init__(self, data):
        self.data = memoryview(data)
        order = bytes(self.data[:2])
        if order not in (b"II", b"MM"):
            raise ValueError("not a TIFF file")
        self._bo = "<" if order == b"II" else ">"
        magic = self._unpack("H", 2)
        if magic == 42:
            self._big, first = False, self._unpack("I", 4)
        elif magic == 43:
            self._big, first = True, self._unpack("Q", 8)
        else:
            raise ValueError(f"not a TIFF file (magic {magic})")
        self.tags = self._ifd(first)
        self._check()

    # -- structure ----------------------------------------------------------------------------------

    def _unpack(self, code, at):
        return struct.unpack_from(self._bo + code, self.data, at)[0]

    def _ifd(self, at):
        """{tag: value tuple (or str for ASCII)} of the image file directory at offset `at`."""
        count_code, entry_size, head = ("Q", 20, 8) if self._big else ("H", 12, 2)
        count = self._unpack(count_code, at)
        tags = {}
        for k in range(count):
            e = at + head + k * entry_size
            tag, kind = struct.unpack_from(self._bo + "HH", self.data, e)
            n = self._unpack("Q" if self._big else "I", e + 4)
            if kind not in _TYPES:
                continue  # a type this reader doesn't know can't be one of its tags
            code, size = _TYPES[kind]
            inline = 8 if self._big else 4
            value_at = e + (12 if self._big else 8)
            if n * size > inline:
                value_at = self._unpack("Q" if self._big else "I", value_at)
            if kind == 2:
                tags[tag] = bytes(self.data[value_at : value_at + n]).rstrip(b"\0").decode("latin-1")
            else:
                parts = len(code)  # rationals are two integers each
                tags[tag] = struct.unpack_from(f"{self._bo}{n * parts}{code[0]}", self.data, value_at)
        return tags

    def _check(self):
        t = self.tags
        self.width, self.height = t[WIDTH][0], t[HEIGHT][0]
        if t.get(SAMPLES, (1,))[0] != 1:
            raise ValueError("only single-band TIFFs are read")
        bits = t.get(BITS, (1,))[0]
        kind = _KINDS.get(t.get(SAMPLE_FORMAT, (1,))[0])
        if kind is None or bits not in (8, 16, 32, 64) or (kind == "f" and bits < 32):
            raise ValueError(f"unsupported samples: {bits}-bit format {t.get(SAMPLE_FORMAT)}")
        self.dtype = np.dtype(f"{self._bo}{kind}{bits // 8}")
        self.compression = t.get(COMPRESSION, (NONE,))[0]
        if self.compression not in (NONE, LZW, DEFLATE, DEFLATE_OLD):
            raise ValueError(f"unsupported compression {self.compression}")
        self.predictor = t.get(PREDICTOR, (1,))[0]
        if self.predictor not in (1, 2) or (self.predictor == 2 and kind == "f"):
            raise ValueError(f"unsupported predictor {self.predictor}")
        if TILE_OFFSETS in t:
            self.block_w, self.block_h = t[TILE_WIDTH][0], t[TILE_HEIGHT][0]
            self._offsets, self._sizes = t[TILE_OFFSETS], t[TILE_BYTES]
        else:
            self.block_w, self.block_h = self.width, t.get(ROWS_PER_STRIP, (self.height,))[0]
            self.block_h = min(self.block_h, self.height)
            self._offsets, self._sizes = t[STRIP_OFFSETS], t[STRIP_BYTES]
        self._across = -(-self.width // self.block_w)
        if len(self._offsets) != self._across * -(-self.height // self.block_h):
            raise ValueError("the block offsets don't cover the image")

    # -- georeference -------------------------------------------------------------------------------

    @property
    def grid(self):
        """The pixel grid (Grid), from the pixel scale and the first tie point."""
        if PIXEL_SCALE not in self.tags or TIE_POINT not in self.tags:
            raise ValueError("no pixel scale and tie point: not a georeferenced grid")
        dx, dy = self.tags[PIXEL_SCALE][:2]
        i, j, _, x, y, _ = self.tags[TIE_POINT][:6]
        return Grid(x - i * dx, y + j * dy, dx, dy)

    @property
    def nodata(self):
        """GDAL's no-data value, or None."""
        text = self.tags.get(NODATA, "").strip()
        return float(text) if text else None

    @property
    def crs_text(self):
        """The GeoTIFF ASCII parameters (citations such as "World_Mollweide|WGS 84|..."), or ""."""
        return self.tags.get(GEO_ASCII, "")

    # -- pixels -------------------------------------------------------------------------------------

    def row_bands(self):
        """(first row, array of shape (rows, width)) for each band of strips or tiles, top down."""
        same = {}
        for band in range(-(-self.height // self.block_h)):
            top = band * self.block_h
            rows = min(self.block_h, self.height - top)
            out = np.empty((rows, self.width), dtype=self.dtype)
            for k in range(self._across):
                block = self._block(band * self._across + k, same)
                left = k * self.block_w
                cols = min(self.block_w, self.width - left)
                out[:, left : left + cols] = block[:rows, :cols]
            yield top, out

    def _block(self, index, same):
        at, size = self._offsets[index], self._sizes[index]
        raw = bytes(self.data[at : at + size])
        if size <= _SAME_TILE_BYTES and raw in same:
            return same[raw]
        block = self._decode(raw)
        if size <= _SAME_TILE_BYTES:
            block.flags.writeable = False
            same[raw] = block
        return block

    def _decode(self, raw):
        if self.compression == LZW:
            raw = lzw.decode(raw)
        elif self.compression in (DEFLATE, DEFLATE_OLD):
            raw = zlib.decompress(raw)
        rows = len(raw) // (self.block_w * self.dtype.itemsize)
        block = np.frombuffer(raw, dtype=self.dtype, count=rows * self.block_w).reshape(rows, self.block_w)
        if self.predictor == 2:  # each sample stored as the difference from its left neighbour
            unsigned = block.dtype.newbyteorder("=").str.replace("i", "u")
            block = np.cumsum(block.astype(unsigned), axis=1, dtype=unsigned).view(
                block.dtype.newbyteorder("=")
            )
        return block
