"""The minimal GeoTIFF reader and TIFF LZW (packbuild.sources.ghsl.geotiff, .lzw), on files the
test kit writes: every layout the reader claims, read back pixel for pixel."""

import itertools

import numpy as np
import pytest
from ghsl_kit import lzw_encode, write_tiff

from packbuild.sources.ghsl import lzw
from packbuild.sources.ghsl.geotiff import GeoTiff, Grid


def test_lzw_round_trip_across_code_widths_and_clears():
    rng = np.random.default_rng(1)
    for data in (b"", b"a", b"abababababab" * 50, rng.integers(0, 4, 40_000, dtype=np.uint8).tobytes(),
                 rng.integers(0, 256, 20_000, dtype=np.uint8).tobytes()):  # fmt: skip
        assert lzw.decode(lzw_encode(data)) == data


def test_lzw_kwkwk_code():
    # "aaa...": each code refers to the entry being defined
    assert lzw.decode(lzw_encode(b"a" * 1000)) == b"a" * 1000


def test_lzw_rejects_codes_past_the_table():
    bad = bytes([0b10000000, 0b01111111, 0b11000000, 0])  # CLEAR, then code 511 at once
    with pytest.raises(ValueError):
        lzw.decode(bad)


@pytest.mark.parametrize(
    ("tile", "compression", "predictor", "big", "order", "dtype"),
    [
        (t, c, p, b, o, d)
        for t, c, p, b, o, d in itertools.product(
            [(16, 16), None], [1, 5, 8], [1, 2], [False, True], ["<", ">"], ["int16", "uint8"]
        )
    ],
)
def test_reads_every_layout(tile, compression, predictor, big, order, dtype):
    rng = np.random.default_rng(5)
    image = rng.choice(np.array([-200, 10, 11, 21, 22, 23, 30]) if dtype == "int16" else np.arange(5),
                       size=(37, 45)).astype(dtype)  # fmt: skip
    raw = write_tiff(image, tile=tile, rows_per_strip=7, compression=compression, predictor=predictor,
                     big=big, order=order)  # fmt: skip
    tif = GeoTiff(raw)
    assert (tif.width, tif.height) == (45, 37)
    bands = list(tif.row_bands())
    assert [top for top, _ in bands] == list(range(0, 37, 16 if tile else 7))
    assert np.array_equal(np.vstack([b for _, b in bands]), image)


def test_georeference():
    tif = GeoTiff(write_tiff(np.zeros((3, 4), dtype=np.int16), origin=(-18041000.0, 9000000.0)))
    assert tif.grid == Grid(-18041000.0, 9000000.0, 1000.0, 1000.0)
    assert tif.nodata == -200.0 and tif.crs_text.startswith("World_Mollweide")


def test_float_samples():
    image = np.linspace(0, 1, 30, dtype=np.float32).reshape(5, 6)
    tif = GeoTiff(write_tiff(image, compression=8))
    assert np.array_equal(next(tif.row_bands())[1], image)


def test_refuses_what_it_cannot_read():
    with pytest.raises(ValueError, match="not a TIFF"):
        GeoTiff(b"GIF89a" + bytes(20))
    with pytest.raises(ValueError, match="compression"):
        GeoTiff(write_tiff(np.zeros((2, 2), dtype=np.uint8), compression=7))  # JPEG
    with pytest.raises(ValueError, match="predictor"):
        GeoTiff(write_tiff(np.zeros((2, 2), dtype=np.float32), predictor=2))
