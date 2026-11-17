# ruff: noqa: E501  (data rows are longer than a line)
"""OMB delineation list 2: the principal cities of every metro and micro area."""

import pytest
from us_fixtures import write_xlsx

from packbuild.sources.usa import principal

HEADER = ("CBSA Code", "CBSA Title", "Metropolitan/Micropolitan Statistical Area", "Principal City Name",
          "FIPS State Code", "FIPS Place Code")  # fmt: skip
ROWS = [  # as in list2_2023.xlsx: alphabetical by state, then name, within each CBSA
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Henderson", "32", "31900"),
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Las Vegas", "32", "40000"),
    ("29820", "Las Vegas-Henderson-North Las Vegas, NV", "Metropolitan Statistical Area", "Paradise", "32", "54600"),
    ("47900", "Washington-Arlington-Alexandria, DC-VA-MD-WV", "Metropolitan Statistical Area", "Washington", "11",
     "50000"),
    ("47900", "Washington-Arlington-Alexandria, DC-VA-MD-WV", "Metropolitan Statistical Area", "Alexandria", "51",
     "01000"),
    ("47900", "Washington-Arlington-Alexandria, DC-VA-MD-WV", "Metropolitan Statistical Area", "Arlington", "51",
     "03000"),
    ("21220", "Elko, NV", "Micropolitan Statistical Area", "Elko", "32", "22500"),
]  # fmt: skip


@pytest.fixture
def list2(tmp_path):
    rows = [
        ("Table with row headers in column A and column headers in row 3",),
        ("List 2. PRINCIPAL CITIES OF METROPOLITAN AND MICROPOLITAN STATISTICAL AREAS, JULY 2023",),
        HEADER,
        *ROWS,
        (),
        ("Note: The Office of Management and Budget's (OMB's) 2020 Standards ...",),
    ]
    return write_xlsx(tmp_path / "list2_2023.xlsx", rows)


def test_rows_with_place_geoids(list2):
    rows = principal.read_principal_cities(list2)
    assert len(rows) == 7
    assert rows[1] == {"cbsa": "29820", "type": "metro", "name": "Las Vegas", "place": "3240000"}
    assert rows[-1]["type"] == "micro"


def test_ordered_largest_first_the_rule_cbsa_titles_follow(list2):
    rows = principal.read_principal_cities(list2)
    population = {"3240000": 679817, "3231900": 349471, "3254600": 185913, "1150000": 702250,
                  "5101000": 155230, "5103000": 236254}  # fmt: skip
    order = principal.ordered(rows, population)
    assert order["29820"] == ["3240000", "3231900", "3254600"]
    assert order["47900"] == ["1150000", "5103000", "5101000"]
    assert order["21220"] == ["3222500"]  # no population: kept, after any known


def test_a_file_without_the_header_is_refused(tmp_path):
    path = write_xlsx(tmp_path / "list2.xlsx", [("nothing here",)])
    with pytest.raises(ValueError, match="CBSA Code"):
        principal.read_principal_cities(path)
