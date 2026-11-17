"""The pure naming rules: metro titles, roll-ups, census subdivision kinds, post-office names."""

import pytest

from placewise.constants import naming as const
from placewise.engine.naming import rules


def known(*names):
    return set(names).__contains__


def test_metro_title_cities_and_states():
    title = "Las Vegas-Henderson-North Las Vegas, NV"
    assert rules.title_cities(title, known("Las Vegas", "Henderson", "North Las Vegas")) == [
        "Las Vegas",
        "Henderson",
        "North Las Vegas",
    ]
    assert rules.title_states(title) == ["NV"]
    assert rules.title_states("New York-Newark-Jersey City, NY-NJ") == ["NY", "NJ"]


def test_metro_title_keeps_hyphenated_names_whole():
    assert rules.title_cities("Winston-Salem, NC", known("Winston-Salem")) == ["Winston-Salem"]
    nashville = "Nashville-Davidson--Murfreesboro--Franklin, TN"
    assert rules.title_cities(nashville, known("Nashville-Davidson", "Murfreesboro", "Franklin")) == [
        "Nashville-Davidson",
        "Murfreesboro",
        "Franklin",
    ]


def test_metro_title_skips_names_that_are_no_place():
    assert rules.title_cities("Amherst Town-Northampton, MA", known("Northampton")) == ["Northampton"]
    assert rules.title_cities("Nowhere, ZZ", known()) == []


def test_census_metropolitan_area_names():
    assert rules.cma_cities("Kitchener - Cambridge - Waterloo") == ["Kitchener", "Cambridge", "Waterloo"]
    assert rules.cma_cities("Saint-Jean-sur-Richelieu") == ["Saint-Jean-sur-Richelieu"]


@pytest.mark.parametrize(
    ("population", "head", "expected"),
    [
        (99_186, 2_794_356, True),  # Pickering -> Toronto
        (32_901, 136_803, False),  # Fort Erie stays: St. Catharines isn't 10x bigger
        (338_503, 2_794_356, False),  # Markham stays: 100k or more
        (None, 2_794_356, False),  # unknown population: no roll-up
        (5_000, None, False),
    ],
)
def test_roll_up_to_the_metro_head(population, head, expected):
    assert rules.rolls_up(population, head) is expected


def test_roll_up_thresholds_are_the_constants():
    keep, ratio = const.CITY_KEEP_POPULATION, const.CITY_ROLL_UP_RATIO
    assert rules.rolls_up(keep - 1, (keep - 1) * ratio)
    assert not rules.rolls_up(keep, keep * ratio * 10)
    assert not rules.rolls_up(1000, 1000 * ratio - 1)


def test_census_subdivision_kinds():
    assert rules.csd_kind("CY") == rules.MUNICIPAL  # Mississauga
    assert rules.csd_kind("T") == rules.MUNICIPAL  # Fort Erie
    assert rules.csd_kind("TP") == rules.RURAL  # townships
    assert rules.csd_kind("RM") == rules.RURAL
    assert rules.csd_kind("ID") == rules.UNORGANIZED  # Improvement District No. 9 (Banff park)
    assert rules.csd_kind("NO") == rules.UNORGANIZED


@pytest.mark.parametrize(
    ("name", "area"),
    [
        ("Whitefield S.O", "Whitefield"),
        ("DLF QE SO", "DLF QE"),
        ("New Delhi GPO", "New Delhi"),
        ("Peddakotla B.O", "Peddakotla"),
        ("Bangalore H.O", "Bangalore"),
        ("Industrial Complex Dundahera S.O.", "Industrial Complex Dundahera"),
        ("Bengaluru G.P.O.", "Bengaluru"),
        ("Gandhi Bazar SO Amritsar", "Gandhi Bazar"),  # the type, then the town it reports to
        ("Old Town S.O (Khorda)", "Old Town"),
        ("Sohna", "Sohna"),
        ("SO", "SO"),  # nothing left: keep the name
    ],
)
def test_post_office_area_names(name, area):
    assert rules.office_area_name(name) == area


def test_same_name_ignores_case_and_accents():
    assert rules.same_name("Montréal", "MONTREAL")
    assert not rules.same_name("Niagara", "Niagara Falls")
    assert not rules.same_name(None, "Toronto")
