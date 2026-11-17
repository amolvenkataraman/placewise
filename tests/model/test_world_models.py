"""Country, subregion, group and profile models: frozen, validated, and round-tripping through dicts."""

import dataclasses
import json

import pytest

from placewise.model import (
    Country,
    CountryGroup,
    Currency,
    Membership,
    Profile,
    Statistic,
    Subregion,
)


def _round_trip(obj):
    data = json.loads(json.dumps(obj.to_dict()))
    assert type(obj).from_dict(data) == obj
    return data


def test_country_round_trips_and_is_frozen():
    ca = Country("CA", "CAN", "124", "Canada", "Canada", ("Dominion of Canada",))
    assert _round_trip(ca)["alpha3"] == "CAN"
    with pytest.raises(dataclasses.FrozenInstanceError):
        ca.name = "x"
    assert Country("AD", "AND", "020", "Andorra").official_name is None


@pytest.mark.parametrize(
    "args",
    [
        ("C", "CAN", "124", "Canada"),  # alpha-2 must be two capitals
        ("CA", "CA", "124", "Canada"),  # alpha-3 must be three
        ("CA", "CAN", "12", "Canada"),  # numeric is three digits
        ("CA", "CAN", "124", ""),
    ],
)
def test_country_validates_codes(args):
    with pytest.raises(ValueError):
        Country(*args)


def test_subregion_round_trips_with_extra_codes():
    on = Subregion("CA-ON", "ON", "Ontario", "province", "CA", ("Ont.",), {"sgc": "35"})
    data = _round_trip(on)
    assert data["codes"] == {"sgc": "35"} and data["country"] == "CA"
    with pytest.raises(ValueError, match="CA-ON"):
        Subregion("CA-QC", "ON", "Ontario", "province", "CA")  # code must be country-short_code


def test_membership_and_dates():
    m = Membership("GB", since="1973-01-01", until="2020-01-31")
    assert _round_trip(m) == {"country": "GB", "since": "1973-01-01", "until": "2020-01-31"}
    assert Membership("NO", since="1949").since == "1949"  # a year alone is kept as written
    with pytest.raises(ValueError):
        Membership("GB", since="2020-02-30")
    with pytest.raises(ValueError):
        Membership("GB", since="2020", until="2019")


def test_country_group_round_trips():
    group = CountryGroup(
        id="legal:demo",
        name="Demo Union",
        aliases=("DU",),
        kind="union",
        category="legal",
        members=(Membership("FR", "1958-01-01"), Membership("GB", "1973", "2020-01-31")),
        source="https://example.org",
        notes="for tests",
        other_members=("legal:eu",),
    )
    data = _round_trip(group)
    assert data["members"][1] == {"country": "GB", "since": "1973", "until": "2020-01-31"}
    with pytest.raises(ValueError, match="category"):
        dataclasses.replace(group, category="other")


def test_profile_round_trips_and_validates():
    profile = Profile(
        code="CA",
        name="Canada",
        kind="country",
        alpha2="CA",
        alpha3="CAN",
        capital="Ottawa",
        currency=Currency("CAD", "Canadian Dollar", "CA$", "$"),
        calling_code="+1",
        languages=("en-CA", "fr-CA"),
        measurement_system="metric",
        driving_side="right",
        first_day_of_week="sunday",
        time_zones=("America/Toronto",),
        population=Statistic(41651653, "geonames", None),
        area_km2=Statistic(9984670.0, "geonames", None),
        neighbours=("US",),
    )
    data = _round_trip(profile)
    assert data["currency"]["code"] == "CAD" and data["population"]["value"] == 41651653
    assert Profile(code="AQ", name="Antarctica", kind="country", alpha2="AQ", alpha3="ATA").currency is None
    for field, bad in [("measurement_system", "furlongs"), ("driving_side", "middle")]:
        with pytest.raises(ValueError, match=field):
            dataclasses.replace(profile, **{field: bad})
    with pytest.raises(ValueError):
        dataclasses.replace(profile, first_day_of_week="caturday")
