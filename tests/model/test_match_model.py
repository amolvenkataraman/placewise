"""Result.matches: how each place-valued field was filled (Match), its dict round trip and helpers."""

import dataclasses
import json

import pytest
from display_kit import yosemite_valley

from placewise.model import Match, Relation, Result


def test_match_validates_and_round_trips():
    m = Match(Relation.NEAR, 21.4)
    assert m.relation is Relation.NEAR and Match("within", 0.0).relation is Relation.WITHIN
    assert Match.from_dict(m.to_dict()) == m and m.to_dict() == {"relation": "near", "distance_km": 21.4}
    with pytest.raises(ValueError):
        Match(Relation.NEAR, -1.0)
    assert Match(Relation.NEAR).distance_km is None  # a fallback whose distance isn't known


def test_result_matches_round_trip_and_helpers():
    r = dataclasses.replace(
        yosemite_valley(),
        matches={"city": Match(Relation.NEAR, 3.1), "locality": Match(Relation.WITHIN, 0.0)},
    )
    data = json.loads(json.dumps(r.to_dict()))
    assert data["matches"]["city"] == {"relation": "near", "distance_km": 3.1}
    assert Result.from_dict(data) == r
    assert r.city_within is False and r.locality_within is True and r.city_km == 3.1
    bare = Result(lat=1.0, lon=2.0)
    assert bare.matches == {} and bare.city_within is False and bare.city_km is None
    assert "matches" not in bare.to_dict()
