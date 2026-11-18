from placewise.constants import names
from placewise.model import PlaceKind


def test_place_kind_codes_follow_place_kind():
    assert names.PLACE_KINDS == tuple(k.value for k in PlaceKind)


def test_name_kind_codes():
    assert names.NAME_KINDS[names.OFFICIAL] == "official"
    assert names.NAME_KINDS[names.CODE] == "code"
    assert len(set(names.NAME_KINDS)) == len(names.NAME_KINDS)
