"""placewise.overrides.names: forward search by override (resolve_name)."""

from overrides_kit import DATA_BAY_AREA, GTA_MEMBERS, MISSISSAUGA, engine


def test_resolve_name_returns_alias_targets():
    eng = engine(
        repo={
            "alias": [
                {"text": "GTA", "means": "placewise:region/gta"},
                {"text": "The Bay", "means": DATA_BAY_AREA.id, "country": "US"},
            ],
            "rename": [{"id": MISSISSAUGA.id, "name": "Sauga", "aliases": ["The Sauga"]}],
            "region": [
                {"id": "placewise:region/905", "label": "The 905", "aliases": ["905"], "members": GTA_MEMBERS}
            ],
        }
    )
    assert eng.resolve_name("gta") == ["placewise:region/gta"]
    assert eng.resolve_name("  the   bay ") == [DATA_BAY_AREA.id]
    assert eng.resolve_name("The Bay", country="CA") == []
    assert eng.resolve_name("The Bay", country="US") == [DATA_BAY_AREA.id]
    assert eng.resolve_name("the sauga") == [MISSISSAUGA.id]
    assert eng.resolve_name("905") == ["placewise:region/905"]
    assert eng.resolve_name("Narnia") == []
