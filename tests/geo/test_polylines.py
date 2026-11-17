"""Encoded polylines against Google's "Encoded Polyline Algorithm Format" page:
https://developers.google.com/maps/documentation/utilities/polylinealgorithm
"""

import numpy as np
import pytest

from placewise.geo.polylines import polyline_decode, polyline_encode

# the worked example on Google's page
GOOGLE_POINTS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
GOOGLE_TEXT = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


def test_encode_matches_googles_example():
    assert polyline_encode(GOOGLE_POINTS) == GOOGLE_TEXT


def test_encode_accepts_an_n_by_2_array():
    assert polyline_encode(np.array(GOOGLE_POINTS)) == GOOGLE_TEXT


def test_decode_matches_googles_example():
    points = polyline_decode(GOOGLE_TEXT)
    assert isinstance(points, np.ndarray) and points.shape == (3, 2)
    np.testing.assert_allclose(points, GOOGLE_POINTS, atol=1e-12)


def test_single_value_steps_from_googles_page():
    # the page encodes -179.9832104 step by step to "`~oia@"; a zero delta is chr(63) = "?"
    assert polyline_encode([(-179.9832104, 0.0)]) == "`~oia@?"
    np.testing.assert_allclose(polyline_decode("`~oia@?"), [(-179.98321, 0.0)], atol=1e-12)


def test_precision_6_scales_the_integers_not_the_format():
    # at precision 6 (OSRM, Valhalla) these points have the same integers as Google's example at 5
    tenth = [(lat / 10, lon / 10) for lat, lon in GOOGLE_POINTS]
    assert polyline_encode(tenth, precision=6) == GOOGLE_TEXT
    np.testing.assert_allclose(polyline_decode(GOOGLE_TEXT, precision=6), tenth, atol=1e-12)


def test_precision_6_round_trip_keeps_six_decimals():
    # open-ocean points (Atlantic, Gulf of Guinea), the Arctic Ocean near the pole and the South Pole
    points = np.array([(0.123456, -25.654321), (-1.5, 3.25), (89.999999, -179.999999), (-90.0, 180.0)])
    np.testing.assert_allclose(polyline_decode(polyline_encode(points, 6), 6), points, atol=5e-7)


def test_empty_input_and_output():
    assert polyline_encode([]) == ""
    decoded = polyline_decode("")
    assert decoded.shape == (0, 2)


def test_decode_rejects_truncated_text():
    with pytest.raises(ValueError):
        polyline_decode(GOOGLE_TEXT[:-1])
    with pytest.raises(ValueError):
        polyline_decode("_p~iF")  # a latitude without its longitude
