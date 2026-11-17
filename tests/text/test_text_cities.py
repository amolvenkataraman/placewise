"""Known cities: the generated GeoNames list and the regions' principal cities."""

from placewise.text import cities


def test_known_cities():
    assert cities.is_known("Toronto", "CA", "ON")
    assert cities.is_known("Mississauga", "CA", "ON")
    assert cities.is_known("St Paul", "US", "MN")  # "Saint Paul": St / Saint compare equal
    assert not cities.is_known("Toronto", "US", "CA")
    assert cities.admin1s("Ottawa", "CA") == {"ON"}
    assert cities.admin1s("Atlantis", "CA") == set()
