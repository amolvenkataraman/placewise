"""world.country and world.countries: lookups by code or name, and lists by group, continent and date."""

import datetime as dt

import pytest

from placewise import world
from placewise.model import Country


@pytest.mark.parametrize("given", ["CA", "ca", "CAN", "can", "124", 124, "Canada", "canada", " CANADA "])
def test_country_by_code_or_name(given):
    ca = world.country(given)
    assert isinstance(ca, Country)
    assert (ca.alpha2, ca.alpha3, ca.numeric, ca.name) == ("CA", "CAN", "124", "Canada")


def test_country_by_alias_and_official_name():
    assert world.country("U.S.").alpha2 == "US"
    assert world.country("UK").alpha2 == "GB"
    assert world.country("Holland").alpha2 == "NL"
    assert world.country("US").official_name == "United States of America"
    assert world.country("FR").official_name is None  # no sourced official name: left out


def test_unknown_country_names_the_input_and_suggests():
    with pytest.raises(KeyError, match="Canda") as info:
        world.country("Canda")
    assert "Canada" in str(info.value)
    with pytest.raises(KeyError, match="no country"):
        world.country("XX")


def test_countries_without_filters_is_every_iso_country_sorted_by_name():
    every = world.countries()
    assert len(every) == 249
    assert [c.name for c in every] == sorted(c.name for c in every)


def test_countries_in_a_group_by_alias():
    assert [c.alpha2 for c in world.countries(group="US & Canada")] == ["CA", "US"]
    assert {c.alpha2 for c in world.countries(group="DACH")} == {"AT", "CH", "DE"}
    assert {c.alpha2 for c in world.countries(group="CANZUK")} == {"AU", "CA", "GB", "NZ"}
    assert "FR" in {c.alpha2 for c in world.countries(group="Western Europe")}
    assert "ZA" in {c.alpha2 for c in world.countries(group="EMEA")}
    assert len(world.countries(group="EU")) == 27


def test_eu_membership_through_time():
    in_eu = lambda day: "GB" in {c.alpha2 for c in world.countries(group="EU", as_of=day)}  # noqa: E731
    assert in_eu("2019-06-01")
    assert in_eu(dt.date(2020, 1, 31))  # its last day
    assert not in_eu("2021-01-01")
    assert not in_eu(None)  # today
    assert "HR" not in {c.alpha2 for c in world.countries(group="EU", as_of="2010-01-01")}


def test_a_list_of_groups_is_their_intersection():
    both = {c.alpha2 for c in world.countries(group=["EU", "NATO"])}
    assert "FR" in both and "AT" not in both and "NO" not in both
    assert {c.alpha2 for c in world.countries(group=["Schengen", "EFTA"])} == {"CH", "IS", "LI", "NO"}


def test_filters_combine():
    europe_eu = world.countries(group="EU", continent="Europe")
    assert "CY" not in {c.alpha2 for c in europe_eu}  # Cyprus: EU, but Asia by UN M49
    assert {c.alpha2 for c in world.countries(continent="oceania")} >= {"AU", "NZ", "FJ"}
    unions = {c.alpha2 for c in world.countries(kind="currency-union")}
    assert "DE" in unions and "GB" not in unions


def test_bad_filters_say_what_is_wrong():
    with pytest.raises(KeyError, match="Atlantis"):
        world.countries(group="Atlantis")
    with pytest.raises(KeyError, match="EU"):
        world.countries(continent="EU")  # a group, but not a continent
    with pytest.raises(ValueError, match="kind"):
        world.countries(kind="planet")
    with pytest.raises(ValueError, match="date"):
        world.countries(group="EU", as_of="last tuesday")


def test_lazy_top_level_names():
    import placewise

    assert placewise.country is world.country and placewise.countries is world.countries
    assert placewise.world is world
