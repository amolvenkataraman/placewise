"""Plus codes against the official Open Location Code test data (vendored in data/plus_codes)."""

import csv
from pathlib import Path

import numpy as np
import pytest

from placewise.geo import plus_codes as pc

DATA = Path(__file__).parent / "data" / "plus_codes"


def _rows(name):
    with open(DATA / name, encoding="utf-8", newline="") as f:
        return [row for row in csv.reader(f) if row and not row[0].lstrip().startswith("#")]


ENCODING = _rows("encoding.csv")  # lat, lng, lat int, lng int, length, code
DECODING = _rows("decoding.csv")  # code, length, latLo, lngLo, latHi, lngHi
SHORT = _rows("shortCodeTests.csv")  # full code, lat, lng, short code, R/S/B
VALIDITY = _rows("validityTests.csv")  # code, isValid, isShort, isFull


def test_the_vendored_data_was_read():
    assert len(ENCODING) > 250 and len(DECODING) > 400 and len(SHORT) > 15 and len(VALIDITY) > 20


@pytest.mark.parametrize(("lat", "lng", "length", "expected"), [(r[0], r[1], r[4], r[5]) for r in ENCODING])
def test_encode_matches_official_data(lat, lng, length, expected):
    if not expected:
        with pytest.raises(ValueError):
            pc.encode(float(lat), float(lng), int(length))
    else:
        assert pc.encode(float(lat), float(lng), int(length)) == expected


@pytest.mark.parametrize(("lat", "lng", "lat_units", "lng_units"), [r[:4] for r in ENCODING])
def test_degrees_to_integers_matches_official_data(lat, lng, lat_units, lng_units):
    # the data's integer columns pin down the one step where float rounding can bite
    assert pc._units(float(lat), float(lng)) == (int(lat_units), int(lng_units))


@pytest.mark.parametrize("row", DECODING, ids=[r[0] for r in DECODING])
def test_decode_matches_official_data(row):
    code, length, south, west, north, east = row[0], int(row[1]), *map(float, row[2:6])
    area = pc.decode(code)
    # the data file asks for agreement to within 1e-10
    assert (area.south, area.west, area.north, area.east) == pytest.approx(
        (south, west, north, east), abs=1e-10
    )
    assert area.centre_lat == pytest.approx((south + north) / 2, abs=1e-10)
    assert area.centre_lon == pytest.approx((west + east) / 2, abs=1e-10)
    assert area.length == length


@pytest.mark.parametrize("row", [r for r in SHORT if r[4] in "SB"], ids=lambda r: f"{r[0]}@{r[1]},{r[2]}")
def test_shorten_matches_official_data(row):
    full, lat, lng, short = row[0], float(row[1]), float(row[2]), row[3]
    assert pc.shorten(full, lat, lng) == short


@pytest.mark.parametrize("row", [r for r in SHORT if r[4] in "RB"], ids=lambda r: f"{r[3]}@{r[1]},{r[2]}")
def test_recover_nearest_matches_official_data(row):
    full, lat, lng, short = row[0], float(row[1]), float(row[2]), row[3]
    assert pc.recover_nearest(short, lat, lng) == full


@pytest.mark.parametrize("row", VALIDITY, ids=[r[0] for r in VALIDITY])
def test_validity_matches_official_data(row):
    code, valid, short, full = row[0], *(v == "true" for v in row[1:4])
    assert (pc.is_valid(code), pc.is_short(code), pc.is_full(code)) == (valid, short, full)


def test_encode_takes_arrays_and_gives_string_arrays():
    # two rows of the official encoding data
    codes = pc.encode(np.array([20.3700625, 47.0000625]), np.array([2.7821875, 8.0000625]))
    assert isinstance(codes, np.ndarray)
    assert list(codes) == ["7FG49QCJ+2V", "8FVC2222+22"]


def test_encode_returns_plain_str_for_scalars():
    assert type(pc.encode(47.0000625, 8.0000625)) is str


@pytest.mark.parametrize("length", [0, 1, 3, 5, 7, 9])
def test_encode_rejects_lengths_the_spec_forbids(length):
    with pytest.raises(ValueError):
        pc.encode(47.0, 8.0, length)


def test_decode_rejects_short_and_invalid_codes():
    for bad in ["2345+G6", "8FWC2_45+G6", "84900000+"]:
        with pytest.raises(ValueError):
            pc.decode(bad)


def test_shorten_rejects_padded_codes_and_recover_rejects_garbage():
    with pytest.raises(ValueError):
        pc.shorten("7FG49Q00+", 20.375, 2.775)
    with pytest.raises(ValueError):
        pc.recover_nearest("8FWC2_45+G6", 47.0, 8.0)


def test_decode_is_frozen():
    area = pc.decode("8FVC2222+22")
    with pytest.raises(AttributeError):
        area.south = 0.0
