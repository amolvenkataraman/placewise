import pytest

from placewise.geo import codes


def test_geohash_reference_value():
    assert codes.geohash_encode(57.64911, 10.40744, precision=11) == "u4pruydqqvj"
    assert codes.geohash_encode(57.64911, 10.40744) == "u4pruydqqv"  # default precision 10 (~1 m)


def test_geohash_decode_contains_the_point():
    lat, lon, lat_err, lon_err = codes.geohash_decode("u4pruydqqvj")
    assert abs(lat - 57.64911) <= lat_err
    assert abs(lon - 10.40744) <= lon_err
    # 11 chars = 28 lon bits + 27 lat bits: both half-cells come out at 180 / 2**28 degrees
    assert lat_err == pytest.approx(180 / 2**28) and lon_err == pytest.approx(180 / 2**28)


@pytest.mark.parametrize("bad", ["u4pa", "U4P!", ""])
def test_geohash_rejects_invalid(bad):
    with pytest.raises(ValueError):
        codes.geohash_decode(bad)


def test_tile_of_a_point():
    assert codes.tile(0, 0, zoom=1) == (1, 1)
    assert codes.tile(85, -180, zoom=1) == (0, 0)
    assert codes.tile(-85, 179.999, zoom=1) == (1, 1)
    assert codes.tile(43.6426, -79.3871, zoom=14) == (4579, 5980)  # CN Tower


def test_tile_bounds():
    max_lat = 85.0511287798066
    assert codes.tile_bounds(0, 0, 0) == pytest.approx((-max_lat, -180, max_lat, 180))
    south, west, north, east = codes.tile_bounds(4579, 5980, 14)
    assert south <= 43.6426 <= north and west <= -79.3871 <= east


def test_quadkey_round_trip():
    assert codes.quadkey(3, 5, 3) == "213"  # Bing Maps documentation example
    assert codes.from_quadkey("213") == (3, 5, 3)
    with pytest.raises(ValueError):
        codes.from_quadkey("2148")
