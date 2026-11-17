import pytest

from placewise.geo import units


@pytest.mark.parametrize(
    ("value", "from_unit", "to_unit", "expected"),
    [
        (1, "mi", "km", 1.609344),
        (1, "nmi", "km", 1.852),
        (1, "ft", "m", 0.3048),
        (2.5, "km", "m", 2500),
        (10, "m/s", "km/h", 36),
        (1, "kn", "km/h", 1.852),
        (60, "mph", "km/h", 96.56064),
    ],
)
def test_convert(value, from_unit, to_unit, expected):
    assert units.convert(value, from_unit, to_unit) == pytest.approx(expected)
    assert units.convert(expected, to_unit, from_unit) == pytest.approx(value)


def test_convert_rejects_unknown_and_mixed_units():
    with pytest.raises(ValueError, match="furlong"):
        units.convert(1, "furlong", "km")
    with pytest.raises(ValueError, match=r"length.*speed"):
        units.convert(1, "km", "km/h")
