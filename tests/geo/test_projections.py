"""Reference values are GeographicLib's, never placewise's own output.

GeoConvert vectors come from the online tool, queried as
    https://geographiclib.sourceforge.io/cgi-bin/GeoConvert?input=<INPUT>&zone=<Z>&prec=<P>
(GeoConvert 2.5.2; zone=-3 is "match input or standard", prec=6 prints UTM to 1 um, prec=9
prints lat/lon to 1e-14 degrees, prec=0 gives 1 m MGRS). The comment next to each vector is the
INPUT (and zone/prec when not the defaults). ECEF/ENU vectors are the worked examples in the
CartConvert man page, https://geographiclib.sourceforge.io/C++/doc/CartConvert.1.html.

Test points are public landmarks or round-number graticule points, nothing else.
"""

import math

import numpy as np
import pytest

from placewise.constants.web_mercator import MAX_LAT
from placewise.constants.wgs84 import A_M, B_M
from placewise.geo import projections as p

MM = 1e-3
DEG = 1e-9

# fmt: off
UTM_FORWARD = [
    # (lat, lon, zone argument, zone, hemisphere, easting, northing)
    # "43.6426 -79.3871" (CN Tower, Toronto)
    (43.6426, -79.3871, None, 17, "N", 630087.375171, 4833442.311881),
    # "-33.8688 151.2093" (Sydney city centre)
    (-33.8688, 151.2093, None, 56, "S", 334368.633648, 6250948.345385),
    # "0.0001 5.9999" (graticule point at the eastern edge of zone 31, on the equator)
    (0.0001, 5.9999, None, 31, "N", 833967.414049, 11.068275),
    # "1 7.4", zone=31 (graticule point forced 4.4 degrees / 490 km off the central meridian)
    (1, 7.4, 31, 31, "N", 990020.601088, 110859.026217),
    # "-1 7.45", zone=31 (the same, south of the equator)
    (-1, 7.45, 31, 31, "S", 995600.241639, 9889133.437894),
    # "60 4.5" (North Sea off Norway: standard zone would be 31, the 32V exception moves it)
    (60, 4.5, None, 32, "N", 249129.548800, 6659949.573583),
    # "78 10" (Svalbard, 31X-37X exception: zone 33, not 32)
    (78, 10, None, 33, "N", 384085.475123, 8663320.201404),
    # "80 22" (Svalbard, zone 35, not 34)
    (80, 22, None, 35, "N", 403186.945226, 8885748.707734),
    # "72.5 23", zone=33 (forced zone, 8 degrees off its central meridian)
    (72.5, 23, 33, 33, "N", 767791.799675, 8062569.133281),
]

UTM_INVERSE = [
    # (zone, hemisphere, easting, northing, lat, lon)
    (17, "N", 630000, 4833000, 43.63863424549689, -79.38828935593267),  # "17n 630000 4833000"
    (56, "S", 334000, 6251000, -33.86827638689175, 151.20532602757184),  # "56s 334000 6251000"
    (31, "N", 990000, 110000, 0.99225145159165, 7.39980508697408),  # "31n 990000 110000"
    (32, "N", 249000, 6660000, 60.00037233361233, 4.49762311602963),  # "32n 249000 6660000"
    (33, "N", 384000, 8663000, 77.99707643878152, 9.99750801231077),  # "33n 384000 8663000"
    (17, "N", 600000, 4800000, 43.34620000938223, -79.76618786224314),  # "17n 600000 4800000"
]

UPS_FORWARD = [
    # (lat, lon, hemisphere, easting, northing)
    (85, 30, "N", 2277728.695691, 1518959.788343),  # "85 30"
    (86, -45, "N", 1685854.780934, 1685854.780934),  # "86 -45"
    (90, 0, "N", 2000000.0, 2000000.0),  # "90 0"
    (-85, -120, "S", 1518959.788343, 1722271.304309),  # "-85 -120"
    (-86, 45, "S", 2314145.219066, 2314145.219066),  # "-86 45"
    (-80.5, 10, "S", 2183555.078319, 3040992.578568),  # "-80.5 10"
    (83.627, -32.664, "N", 1617746.282023, 1403754.916018),  # "83.627 -32.664", zone=0 (Cape Morris Jesup)
]

UPS_INVERSE = [
    ("N", 2277000, 1519000, 85.00358579081049, 29.93693346989292),  # "n 2277000 1519000"
    ("S", 1519000, 1722000, -84.99909296811434, -120.02630505503215),  # "s 1519000 1722000"
]

MGRS_FORWARD = [
    # (lat, lon, precision, expected); GeoConvert prec 0/-1/-2/-4/-5 = 5/4/3/1/0 digits per axis
    (43.6426, -79.3871, 5, "17TPJ3008733442"),  # "43.6426 -79.3871", prec=0
    (43.6426, -79.3871, 4, "17TPJ30083344"),  # prec=-1
    (43.6426, -79.3871, 3, "17TPJ300334"),  # prec=-2
    (43.6426, -79.3871, 1, "17TPJ33"),  # prec=-4
    (43.6426, -79.3871, 0, "17TPJ"),  # prec=-5
    (-33.8688, 151.2093, 5, "56HLH3436850948"),  # "-33.8688 151.2093", prec=0
    (60, 4.5, 5, "32VKM4912959949"),  # "60 4.5", prec=0
    (78, 10, 5, "33XUG8408563320"),  # "78 10", prec=0
    (85, 30, 5, "ZCC7772818959"),  # "85 30", prec=0
    (86, -45, 5, "YUD8585485854"),  # "86 -45", prec=0
    (-85, -120, 5, "ATK1895922271"),  # "-85 -120", prec=0
    (-86, 45, 5, "BFR1414514145"),  # "-86 45", prec=0
    (-80.5, 10, 5, "BBY8355540992"),  # "-80.5 10", prec=0
]

MGRS_INVERSE = [
    # (text, lat, lon) of the cell centre; all queried with prec=9
    ("17TPJ3008733442", 43.64260167133282, -79.38709840758816),
    ("17TPJ300334", 43.64267573330290, -79.38756136737930),
    ("17TPJ33", 43.65574405374734, -79.32582606532672),
    ("17TPJ", 43.78785679263031, -79.13571618691720),
    ("17TPJ123456789012", 44.05467055575542, -79.59744540952361),  # sub-metre digits are legal
    ("56HLH3436850948", -33.86879858520177, 151.20929858481274),
    ("32VKM4912959949", 59.99999931154178, 4.49999921742900),
    ("ZCC7772818959", 84.99999863462379, 29.99996764732417),
    ("ZAA12", 83.92419214893549, 1.27303002005671),
    ("YUB17770380", 83.62751783153258, -32.66423095308052),  # GeoConvert's own documented example
    ("ATK1895922271", -84.99999863462379, -119.99996764732417),
    ("BFR1414514145", -85.99999642566044, 45.0),
    ("BBY8355540992", -80.50000003713276, 10.00002324881510),
]
# fmt: on


@pytest.mark.parametrize(("lat", "lon", "zone_arg", "zone", "hemi", "easting", "northing"), UTM_FORWARD)
def test_to_utm_matches_geoconvert(lat, lon, zone_arg, zone, hemi, easting, northing):
    z, h, e, n = p.to_utm(lat, lon, zone=zone_arg)
    assert (z, h) == (zone, hemi)
    assert type(z) is int and type(h) is str and type(e) is float
    assert e == pytest.approx(easting, abs=MM)
    assert n == pytest.approx(northing, abs=MM)


@pytest.mark.parametrize(("zone", "hemi", "easting", "northing", "lat", "lon"), UTM_INVERSE)
def test_from_utm_matches_geoconvert(zone, hemi, easting, northing, lat, lon):
    assert p.from_utm(zone, hemi, easting, northing) == pytest.approx((lat, lon), abs=DEG)


def test_utm_forward_vectors_also_invert():
    for lat, lon, _, zone, hemi, easting, northing in UTM_FORWARD:
        assert p.from_utm(zone, hemi.lower(), easting, northing) == pytest.approx((lat, lon), abs=1e-10)


def test_to_utm_and_from_utm_vectorise():
    lat, lon = np.array([43.6426, -33.8688, 60, 78]), np.array([-79.3871, 151.2093, 4.5, 10])
    zone, hemi, e, n = p.to_utm(lat, lon)
    assert list(zone) == [17, 56, 32, 33] and list(hemi) == ["N", "S", "N", "N"]
    np.testing.assert_allclose(e, [630087.375171, 334368.633648, 249129.548800, 384085.475123], atol=MM)
    back_lat, back_lon = p.from_utm(zone, hemi, e, n)
    np.testing.assert_allclose(back_lat, lat, atol=1e-10)
    np.testing.assert_allclose(back_lon, lon, atol=1e-10)


def test_utm_refuses_polar_latitudes_and_bad_input():
    for lat in (84, 85, -80.5, -90):
        with pytest.raises(ValueError, match="UPS"):
            p.to_utm(lat, 10)
    with pytest.raises(ValueError):
        p.to_utm(43, -79, zone=61)
    with pytest.raises(ValueError):
        p.from_utm(0, "N", 500000, 0)
    with pytest.raises(ValueError):
        p.from_utm(17, "E", 500000, 0)


def test_to_utm_ups_picks_the_system():
    assert p.to_utm_ups(43.6426, -79.3871)[:2] == (17, "N")
    zone, hemi, e, n = p.to_utm_ups(85, 30)  # zone 0 means UPS, as in GeographicLib
    assert (zone, hemi) == (0, "N")
    assert (e, n) == pytest.approx((2277728.695691, 1518959.788343), abs=MM)
    assert p.from_utm_ups(0, "S", 1519000, 1722000) == pytest.approx(UPS_INVERSE[1][3:], abs=DEG)
    assert p.from_utm_ups(17, "N", 630000, 4833000) == pytest.approx(UTM_INVERSE[0][4:], abs=DEG)


@pytest.mark.parametrize(("lat", "lon", "hemi", "easting", "northing"), UPS_FORWARD)
def test_to_ups_matches_geoconvert(lat, lon, hemi, easting, northing):
    h, e, n = p.to_ups(lat, lon)
    assert h == hemi
    assert e == pytest.approx(easting, abs=MM)
    assert n == pytest.approx(northing, abs=MM)


@pytest.mark.parametrize(("hemi", "easting", "northing", "lat", "lon"), UPS_INVERSE)
def test_from_ups_matches_geoconvert(hemi, easting, northing, lat, lon):
    assert p.from_ups(hemi, easting, northing) == pytest.approx((lat, lon), abs=DEG)


def test_from_ups_at_the_pole():
    # "n 2000000 2000000" gives latitude 90 (longitude is arbitrary there)
    assert p.from_ups("N", 2000000, 2000000)[0] == pytest.approx(90, abs=DEG)
    assert p.from_ups("S", 2000000, 2000000)[0] == pytest.approx(-90, abs=DEG)


@pytest.mark.parametrize(("lat", "lon", "precision", "expected"), MGRS_FORWARD)
def test_to_mgrs_matches_geoconvert(lat, lon, precision, expected):
    assert p.to_mgrs(lat, lon, precision) == expected


def test_to_mgrs_vectorises_and_checks_precision():
    # "43.6426 -79.3871" and "85 30", prec=-4
    assert list(p.to_mgrs(np.array([43.6426, 85]), np.array([-79.3871, 30]), 1)) == ["17TPJ33", "ZCC71"]
    for bad in (-1, 6, 2.5):
        with pytest.raises(ValueError):
            p.to_mgrs(43.6426, -79.3871, bad)


@pytest.mark.parametrize(("text", "lat", "lon"), MGRS_INVERSE)
def test_from_mgrs_returns_cell_centre_like_geoconvert(text, lat, lon):
    assert p.from_mgrs(text) == pytest.approx((lat, lon), abs=DEG)


def test_from_mgrs_accepts_whitespace_and_lowercase():
    assert p.from_mgrs(" 17t pj 30087 33442\n") == p.from_mgrs("17TPJ3008733442")
    assert p.from_mgrs("zcc 77728 18959") == p.from_mgrs("ZCC7772818959")


def test_from_mgrs_corner():
    # "17n 600000 4800000" is the south-west corner of square 17TPJ
    assert p.from_mgrs("17TPJ", centre=False) == pytest.approx(
        (43.34620000938223, -79.76618786224314), abs=DEG
    )


@pytest.mark.parametrize(
    "text",
    [
        "17IPJ",  # GeoConvert: band letter I not in UTM set
        "17TPJ123",  # GeoConvert: not an even number of digits
        "61TPJ12",  # GeoConvert: zone 61 not in [1, 60]
        "0TPJ12",  # GeoConvert: zone 0 not in [1, 60]
        "17TIJ12",  # GeoConvert: column letter I not in zone 17 set
        "17TPJ1a",  # GeoConvert: non-digit
        "ZZZ12",  # GeoConvert: column letter Z not in UPS band Z set
        "ADA12",  # GeoConvert: column letter D not in UPS band A set
        "17TPA12",  # GeoConvert: block PA not in zone/band 17T
        "17TPJ12345678901",  # GeoConvert: odd number of digits
        "17T",  # GeoConvert reads a bare band; placewise requires a 100 km square
        "",
        "17TPJ" + "1" * 24,  # more than 11 digits per axis
        "TPJ12",  # UTM band without a zone
        "17ZPJ12",  # UPS band with a zone
        "ZAQ12",  # row Q is beyond the north polar rows
        "17TPJ12 34 5",
    ],
)
def test_from_mgrs_rejects_invalid(text):
    with pytest.raises(ValueError):
        p.from_mgrs(text)


def test_mgrs_round_trips():
    for _, _, precision, text in MGRS_FORWARD:
        assert p.to_mgrs(*p.from_mgrs(text), precision) == text


def test_ecef_reference_points():
    assert p.to_ecef(0, 0) == (A_M, 0.0, 0.0)
    assert p.to_ecef(90, 0) == pytest.approx((0, 0, B_M), abs=1e-6)
    assert p.to_ecef(-90, 0, 100)[2] == pytest.approx(-B_M - 100, abs=1e-6)
    # CartConvert example: "echo 33.3 44.4 6000 | CartConvert"
    assert p.to_ecef(33.3, 44.4, 6000) == pytest.approx((3816209.60, 3737108.55, 3485109.57), abs=0.005)


def test_from_ecef_reference_points():
    assert p.from_ecef(A_M, 0, 0) == pytest.approx((0, 0, 0), abs=1e-9)
    lat, _, h = p.from_ecef(0, 0, B_M)
    assert (lat, h) == pytest.approx((90, 0), abs=1e-9)
    assert p.from_ecef(3816209.60, 3737108.55, 3485109.57) == pytest.approx((33.3, 44.4, 6000), abs=0.005)
    # CartConvert example deep inside the Earth (inside the evolute, where naive closed forms fail):
    # "echo 30000 30000 0 | CartConvert -r" => 6.483 45 -6335709.73
    lat, lon, h = p.from_ecef(30000, 30000, 0)
    assert (lat, lon) == pytest.approx((6.483, 45), abs=5e-4)
    assert h == pytest.approx(-6335709.73, abs=0.005)


def test_ecef_round_trip_vectorised():
    lat = np.array([0, 43.6426, -33.8688, 89.9999, -90, 60, 1e-9, -45])
    lon = np.array([0, -79.3871, 151.2093, 10, 0, -179.5, 179.9, 100])
    h = np.array([0, 553.3, -100, 35786e3, 8848, -5000, 1e5, 20e6])
    back = p.from_ecef(*p.to_ecef(lat, lon, h))
    np.testing.assert_allclose(back[0], lat, atol=1e-11)
    not_pole = np.abs(lat) != 90  # longitude is arbitrary at a pole
    np.testing.assert_allclose(back[1][not_pole], lon[not_pole], atol=1e-11)
    np.testing.assert_allclose(back[2], h, atol=1e-6)


def test_enu_matches_cartconvert_and_inverts():
    # "echo 33.3 44.4 6000 | CartConvert -l 33 44 20" => 37288.97 33374.29 5783.64
    # The printed up value is 6.6 mm below a 50-digit evaluation of the same formula (5783.6466),
    # so it looks truncated rather than rounded; hence 1 cm here.
    enu = p.ecef_to_enu(*p.to_ecef(33.3, 44.4, 6000), 33, 44, 20)
    assert enu == pytest.approx((37288.97, 33374.29, 5783.64), abs=0.01)
    assert p.enu_to_ecef(*enu, 33, 44, 20) == pytest.approx(p.to_ecef(33.3, 44.4, 6000), abs=1e-6)


def test_aer():
    # the CartConvert local example again, as azimuth/elevation/range
    az, el, rng = p.aer(33, 44, 20, 33.3, 44.4, 6000)
    e, n, u = 37288.97, 33374.29, 5783.64
    assert az == pytest.approx(math.degrees(math.atan2(e, n)), abs=1e-5)
    assert el == pytest.approx(math.degrees(math.atan2(u, math.hypot(e, n))), abs=1e-5)
    assert rng == pytest.approx(math.sqrt(e * e + n * n + u * u), abs=0.01)
    # a point due north of the CN Tower base: azimuth 0, below the horizon by Earth curvature
    az, el, _ = p.aer(43.6426, -79.3871, 0, 43.75, -79.3871, 0)
    assert min(az, 360 - az) == pytest.approx(0, abs=1e-9)
    assert el < 0
    # straight up
    az, el, rng = p.aer(43.6426, -79.3871, 0, 43.6426, -79.3871, 553.3)
    assert (el, rng) == pytest.approx((90, 553.3), abs=1e-6)
    # the CN Tower top (553 m) seen from 20 km due west at ground level is above the horizon
    assert p.aer(43.6426, -79.635, 76, 43.6426, -79.3871, 76 + 553.3)[1] > 0


def test_web_mercator():
    assert p.to_web_mercator(0, 0) == (0.0, 0.0)
    assert p.to_web_mercator(0, 180)[0] == pytest.approx(math.pi * A_M, rel=1e-15)
    assert p.to_web_mercator(0, -180)[0] == pytest.approx(-math.pi * A_M, rel=1e-15)
    assert p.to_web_mercator(MAX_LAT, 0)[1] == pytest.approx(math.pi * A_M, rel=1e-12)
    assert p.to_web_mercator(89.9, 0)[1] == pytest.approx(math.pi * A_M, rel=1e-12)  # clamped
    assert p.to_web_mercator(-90, 0)[1] == pytest.approx(-math.pi * A_M, rel=1e-12)
    # IOGP/EPSG Guidance Note 7-2, Popular Visualisation Pseudo-Mercator worked example:
    # 24d22'54.433"N 100d20'00"W => E -11169055.58, N 2800000.00 (input latitude good to ~3 cm)
    x, y = p.to_web_mercator(24 + 22 / 60 + 54.433 / 3600, -(100 + 20 / 60))
    assert (x, y) == pytest.approx((-11169055.58, 2800000.00), abs=0.03)
    lat, lon = np.array([43.6426, -33.8688, 0]), np.array([-79.3871, 151.2093, 0])
    back = p.from_web_mercator(*p.to_web_mercator(lat, lon))
    np.testing.assert_allclose(back[0], lat, atol=1e-11)
    np.testing.assert_allclose(back[1], lon, atol=1e-11)
