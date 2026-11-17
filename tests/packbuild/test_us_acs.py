"""ACS 5-year table B01003 (total population) from the table-based summary file."""

import pytest

from packbuild.sources.usa import acs

# rows copied from acsdt5y2024-b01003.dat (plus a jammed estimate, which is skipped)
DAT = """\
GEO_ID|B01003_E001|B01003_M001
0100000US|334922499|-555555555
0400000US32|3214363|-555555555
1600000US0620802|111647|3509
1600000US3240000|660400|126
1600000US3254600|185913|4513
1600000US9999999|-666666666|-222222222
860Z200US89109|6504|1081
0600000US2500107000|50101|33
"""


@pytest.fixture
def dat(tmp_path):
    path = tmp_path / "acsdt5y2024-b01003.dat"
    path.write_text(DAT, encoding="utf-8")
    return path


def test_places_and_zctas_by_geoid(dat):
    found = acs.read_population(dat)
    assert found[acs.PLACE] == {"0620802": 111647, "3240000": 660400, "3254600": 185913}
    assert found[acs.ZCTA] == {"89109": 6504}
    assert acs.COUSUB not in found  # only the summary levels asked for


def test_other_summary_levels_on_request(dat):
    assert acs.read_population(dat, (acs.COUSUB,)) == {acs.COUSUB: {"2500107000": 50101}}


def test_vintage_is_the_last_year_in_the_file_name(dat):
    assert acs.vintage(dat) == 2024
    with pytest.raises(ValueError, match=r"acs\.dat"):
        acs.vintage(dat.with_name("acs.dat"))


def test_a_file_that_is_not_b01003_is_refused(tmp_path):
    path = tmp_path / "acsdt5y2024-b01001.dat"
    path.write_text("GEO_ID|B01001_E001|B01001_M001\n", encoding="utf-8")
    with pytest.raises(ValueError, match="B01003_E001"):
        acs.read_population(path)
