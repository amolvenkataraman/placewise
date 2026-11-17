"""placewise.overrides.tuning: tune rules and merged knobs."""

from overrides_kit import KARIYA_PARK, LAKE_ONTARIO, RATTRAY_MARSH, apply, engine, mississauga_result


def test_tune_sets_tier_and_trims_near_entries():
    eng = engine(repo={"tune": [{"id": KARIYA_PARK.id, "tier": 2}, {"kind": "park", "near_km": 5}]})
    out = apply(eng, mississauga_result())
    assert out.within[0].tier == 2 and out.sources["within"] == "override:repo:repo.toml#1"
    assert [n.place.id for n in out.near] == [LAKE_ONTARIO.id]  # Rattray Marsh is 6 km off
    assert out.sources["near"] == "override:repo:repo.toml#2"


def test_tune_knobs_merge_by_precedence():
    eng = engine(
        repo={"tune": [{"kind": "park", "near_km": 5, "boost": 1.5}]},
        local={"tune": [{"id": RATTRAY_MARSH.id, "near_km": 10}]},
    )
    out = apply(eng, mississauga_result())
    assert [n.place.id for n in out.near] == [LAKE_ONTARIO.id, RATTRAY_MARSH.id]
    assert eng.tuning(RATTRAY_MARSH) == {"near_km": 10.0, "boost": 1.5}
    assert eng.tuning(KARIYA_PARK) == {"near_km": 5.0, "boost": 1.5}
    assert eng.tuning(LAKE_ONTARIO) == {}
    assert eng.tuning(id=RATTRAY_MARSH.id) == {"near_km": 10.0}
    assert eng.tuning(kind="park") == {"near_km": 5.0, "boost": 1.5}
