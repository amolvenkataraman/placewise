"""placewise.overrides.engine: precedence across and within layers, apply, relabel and explain."""

from overrides_kit import (
    KARIYA_PARK,
    MISSISSAUGA,
    MISSISSAUGA_PT,
    TORONTO,
    apply,
    engine,
    mississauga_result,
    toronto_result,
)

from placewise.model import Layer
from placewise.overrides import OverrideEngine


def test_precedence_is_by_layer_not_load_order():
    eng = OverrideEngine.from_documents(
        [
            (Layer.LOCAL, {"rename": [{"id": TORONTO.id, "name": "local"}]}, "local:o.toml"),
            (Layer.REPO, {"rename": [{"id": TORONTO.id, "name": "repo"}]}, "repo:r.toml"),
            (Layer.APP, {"rename": [{"id": TORONTO.id, "name": "app"}]}, "app"),
        ]
    )
    assert apply(eng, toronto_result()).locality.name == "local"
    assert [r.origin for r in eng.rules] == ["repo:r.toml#1", "app#1", "local:o.toml#1"]


def test_within_a_layer_the_later_rule_wins():
    eng = engine(repo={"rename": [{"id": TORONTO.id, "name": "first"}, {"id": TORONTO.id, "name": "second"}]})
    out = apply(eng, toronto_result())
    assert out.locality.name == "second"
    assert out.sources["locality"] == "override:repo:repo.toml#2"


def test_apply_returns_a_new_result_and_leaves_the_input_alone():
    before = mississauga_result()
    eng = engine(repo={"rename": [{"id": MISSISSAUGA.id, "name": "Sauga"}]})
    out = apply(eng, before)
    assert before == mississauga_result()
    assert out is not before and out.locality.name == "Sauga"
    assert apply(OverrideEngine.from_documents([]), before) == before
    # data sources for untouched fields are kept
    assert out.sources["locality"].startswith("override:") and "admin1" not in out.sources


def test_relabel_hook_recomposes_the_label_after_name_changes():
    eng = engine(repo={"rename": [{"id": MISSISSAUGA.id, "name": "Sauga"}]})
    out = eng.apply(
        mississauga_result(), *MISSISSAUGA_PT, relabel=lambda r: f"{r.locality.name}, {r.admin1.name}"
    )
    assert out.label == "Sauga, Ontario"
    assert out.sources["label"] == "override:repo:repo.toml#1"


def test_explain_lists_rules_with_origins():
    eng = engine(
        repo={"alias": [{"text": "GTA", "means": "region:gta"}]},
        local={"hide": [{"id": KARIYA_PARK.id}]},
    )
    rows = eng.explain()
    assert [(r["layer"], r["type"], r["origin"]) for r in rows] == [
        ("repo", "alias", "repo:repo.toml#1"),
        ("local", "hide", "local:local.toml#1"),
    ]
    assert rows[0]["rule"] == {"text": "GTA", "means": "region:gta"}
