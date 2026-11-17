"""The e2e kit finds real packs and a lookup over them answers a public landmark."""

from e2e_kit import geocoder


def test_cn_tower_is_in_toronto_ontario_canada():
    r = geocoder("world").lookup(43.6426, -79.3871)
    assert r.cc == "CA"
    assert r.admin1 is not None and r.admin1.id == "iso:CA-ON"
