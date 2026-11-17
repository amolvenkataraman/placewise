import numpy as np
import pytest

from placewise.geo import coords as c

LAT, LON = 43.6425662, -79.3870568  # CN Tower
DMS_LAT, DMS_LON = 43 + 38 / 60 + 33.2 / 3600, -(79 + 23 / 60 + 13.4 / 3600)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("43.6425662, -79.3870568", (LAT, LON)),
        ("43.6425662°, -79.3870568°", (LAT, LON)),  # Google Timeline exports
        ("43.6425662 -79.3870568", (LAT, LON)),
        ("43°38′33.2″N 79°23′13.4″W", (DMS_LAT, DMS_LON)),
        ("43°38'33.2\"N, 79°23'13.4\"W", (DMS_LAT, DMS_LON)),
        ("43 38 33.2 N 79 23 13.4 W", (DMS_LAT, DMS_LON)),
        ("N 43° 38.5540', W 79° 23.2234'", (43 + 38.5540 / 60, -(79 + 23.2234 / 60))),  # geocaching style
        ("43.64257N 79.38706W", (43.64257, -79.38706)),
        ("79°23′13.4″W 43°38′33.2″N", (DMS_LAT, DMS_LON)),  # hemisphere letters decide the order
        ("-33.8688, 151.2093", (-33.8688, 151.2093)),
        ("https://www.openstreetmap.org/#map=15/43.6426/-79.3871", (43.6426, -79.3871)),
        ("https://www.google.com/maps/@43.6425662,-79.3870568,15z", (LAT, LON)),
        (
            "https://www.google.com/maps/place/X/@43.64,-79.38,17z/data=!3m1?q=43.6425662,-79.3870568",
            (LAT, LON),
        ),
    ],
)
def test_parse(text, expected):
    assert c.parse(text) == pytest.approx(expected, abs=1e-6)


@pytest.mark.parametrize(
    "text", ["95, 10", "10, 200", "hello", "43.64", "43°38′N 43°38′N", "43 61 0 N 79 0 0 W"]
)
def test_parse_rejects_bad_input(text):
    with pytest.raises(ValueError):
        c.parse(text)


def test_from_e7_and_exif():
    assert c.from_e7(436425662, -793870568) == pytest.approx((LAT, LON))
    lat = c.from_exif(((43, 1), (38, 1), (332, 10)), "N")
    lon = c.from_exif(((79, 1), (23, 1), (134, 10)), "W")
    assert (lat, lon) == pytest.approx((DMS_LAT, DMS_LON))


def test_format_dms_and_decimal():
    assert c.format_dms(LAT, LON) == "43°38′33.2″N 79°23′13.4″W"
    assert c.format_dms(10.99999999, -0.00000001) == "11°00′00.0″N 0°00′00.0″W"  # rounding carries
    assert c.format_decimal(LAT, LON, places=5) == "43.64257, -79.38706"
    assert c.parse(c.format_dms(-33.8688, 151.2093)) == pytest.approx((-33.8688, 151.2093), abs=1e-4)


def test_normalize_and_validate():
    assert c.normalize_lon(190) == -170
    assert c.normalize_lon(180) == -180
    np.testing.assert_allclose(c.normalize_lon(np.array([-190, 359, 0])), [170, -1, 0])
    c.validate(90, -180)
    for bad in [(91, 0), (0, float("nan")), (float("inf"), 0)]:
        with pytest.raises(ValueError):
            c.validate(*bad)
    with pytest.raises(ValueError):
        c.validate(np.array([0, 100]), np.array([0, 0]))
