"""world.group, world.groups, world.members and world.is_member, and the metro regions."""

import pytest

from placewise import world
from placewise.model import CountryGroup, Membership


def test_group_by_id_name_or_alias():
    eu = world.group("EU")
    assert isinstance(eu, CountryGroup)
    assert (eu.id, eu.name, eu.category, eu.kind) == ("legal:eu", "European Union", "legal", "union")
    assert eu.source.startswith("https://") and eu.notes
    assert Membership("GB", "1973-01-01", "2020-01-31") in eu.members
    assert world.group("legal:eu") == eu == world.group("european union")
    assert world.group("US and Canada").id == "geo:us-canada"
    assert world.group("Western Europe").category == "geographic"


def test_unknown_group_suggests():
    with pytest.raises(KeyError, match="Schengn") as info:
        world.group("Schengn")
    assert "Schengen" in str(info.value)


def test_non_country_members_are_kept_apart():
    g20 = world.group("G20")
    assert set(g20.other_members) == {"legal:eu", "legal:african-union"}
    assert all(len(m.country) == 2 for m in g20.members)


def test_groups_of_canada():
    legal = {g.id for g in world.groups(of="CA", category="legal")}
    assert {
        "legal:cusma",
        "legal:g7",
        "legal:nato",
        "legal:five-eyes",
        "legal:canzuk",
        "legal:oecd",
        "legal:commonwealth",
    } <= legal
    assert "legal:eu" not in legal
    geographic = {g.id for g in world.groups(of="Canada", category="geographic")}
    assert {"geo:north-america", "geo:us-canada"} <= geographic


def test_groups_filters():
    assert {g.kind for g in world.groups(kind="alliance")} == {"alliance"}
    assert all(g.category == "geographic" for g in world.groups(category="geographic"))
    assert "legal:eu" in {g.id for g in world.groups(of="GB", as_of="2019-06-01")}
    assert "legal:eu" not in {g.id for g in world.groups(of="GB", as_of="2021-01-01")}
    with pytest.raises(ValueError, match="category"):
        world.groups(category="other")


def test_members_and_is_member():
    assert len(world.members("EU")) == 27
    assert "GB" in {c.alpha2 for c in world.members("EU", as_of="2019-06-01")}
    assert world.is_member("NO", "Schengen")
    assert not world.is_member("NO", "EU")
    assert world.is_member("Norway", "EEA")
    assert world.is_member("GB", "EU", on="2019-06-01")
    assert not world.is_member("GB", "EU", on="2021-01-01")
    assert world.is_member("FR", "Western Europe", on="1900-01-01")  # geographic: undated


def test_world_group_covers_every_country():
    assert len(world.members("Worldwide")) == 249


def test_regions_are_the_curated_metros():
    every = world.regions()
    assert any(r.key == "GTA" for r in every)
    canada = world.regions("Canada")
    assert canada and all(r.country == "CA" for r in canada)
    assert {r.country for r in world.regions("IN")} == {"IN"}
    assert world.regions("FR") == []
