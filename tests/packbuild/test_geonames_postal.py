# ruff: noqa: E501  (data rows are longer than a line)
"""packbuild.sources.geonames_postal: GeoNames' world postal codes as the world-postal pack's
`postal` points, offline (a synthetic allCountries.zip of public places)."""

import math
import zipfile

import numpy as np
import pytest

from packbuild.sources import geonames_postal as gp

# country, code, place, admin1, admin1 code, admin2, admin2 code, admin3, admin3 code, lat, lon, accuracy
# fmt: off
ROWS = [
    ("FR", "75007", "Paris 07", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8565", "2.321", "5"),
    ("FR", "75007", "Paris", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8534", "2.3488", "5"),
    ("FR", "75001", "Paris 01", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8592", "2.3417", "5"),
    ("FR", "75001", "Paris", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8534", "2.3488", "5"),
    ("FR", "75008", "Paris 08", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8718", "2.3133", "5"),
    ("FR", "75008", "Paris", "Île-de-France", "11", "Paris", "75", "Paris", "751", "48.8534", "2.3488", "5"),
    ("FR", "75700 CEDEX", "Paris", "Île-de-France", "11", "Paris", "75", "", "", "48.85", "2.30", "5"),
    ("DE", "10117", "Berlin", "Land Berlin", "BE", "", "00", "Berlin, Stadt", "11000", "52.517", "13.3872", "6"),
    ("DE", "10117", "Berlin", "Land Berlin", "BE", "", "00", "Berlin, Stadt", "11000", "52.517", "13.3872", "6"),
    ("DE", "10099", "Humboldt-Universität", "Land Berlin", "BE", "", "", "Berlin, Stadt", "11000", "52.5176", "13.3938", ""),
    ("GB", "SW1A", "Westminster Abbey", "England", "ENG", "Greater London", "", "", "", "51.5018", "-0.1328", "1"),
    ("GB", "BT1", "Belfast", "Northern Ireland", "NIR", "Belfast", "BFS", "", "", "54.5833", "-5.9333", "4"),
    ("CZ", "100 00", "Praha 10", "Hlavní město Praha", "", "", "", "", "", "50.0673", "14.4603", "4"),
    ("US", "10001", "New York", "New York", "NY", "", "", "", "", "40.75", "-73.99", "4"),
    ("CA", "M5V", "Toronto", "Ontario", "ON", "", "", "", "", "43.64", "-79.39", "6"),
    ("IN", "110001", "Connaught Place", "Delhi", "DL", "", "", "", "", "28.63", "77.21", "4"),
    ("SG", "018906", "Straits Boulevard", "", "", "", "", "", "", "1.2758", "103.8496", ""),
    ("GL", "2412", "Santa Claus/Julemanden", "", "", "", "", "", "", "90", "0", ""),
    ("PN", "PCRN 1ZZ", "Pitcairn Islands", "", "", "", "", "", "", "-25.0667", "-130.1", "4"),
    ("AU", "2000", "Sydney", "New South Wales", "NSW", "Sydney", "17200", "", "", "-33.8703", "151.2073", "6"),
    ("AU", "2000", "The Rocks", "New South Wales", "NSW", "Sydney", "17200", "", "", "-33.8605", "151.2073", "6"),
    ("JP", "100-0005", "Marunouchi", "Tokyo To", "40", "Chiyoda Ku", "", "", "", "35.6812", "139.7671", ""),
]
# fmt: on


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / "allCountries.zip"
    text = "".join("\t".join(r) + "\n" for r in ROWS) + "XX\tbroken\n"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("allCountries.txt", text)
    return path


def _codes(rows):
    return [(r.country, r.code) for r in rows]


def test_read_rows_keeps_file_order_and_skips_short_or_unparsable_lines(archive):
    rows = list(gp.read_rows(archive))
    assert len(rows) == len(ROWS)
    first = rows[0]
    assert (first.country, first.code, first.place) == ("FR", "75007", "Paris 07")  # fmt: skip
    assert (first.lat, first.lon) == (48.8565, 2.321)


def test_keep_drops_better_covered_and_undocumented_countries_ni_cedex_and_bad_points(archive):
    kept = {(r.country, r.code) for r in gp.read_rows(archive) if gp.keep(r)}
    for gone in [("US", "10001"), ("CA", "M5V"), ("IN", "110001"), ("SG", "018906")]:
        assert gone not in kept  # country packs do better; undocumented sources
    assert ("GB", "BT1") not in kept  # Northern Ireland: LPS terms
    assert ("FR", "75700 CEDEX") not in kept  # business mail
    assert ("DE", "10099") not in kept  # a German large recipient's own code (no accuracy given)
    assert ("GL", "2412") not in kept  # a point at the pole
    assert {("GB", "SW1A"), ("CZ", "100 00"), ("PN", "PCRN 1ZZ"), ("DE", "10117")} <= kept


def test_points_drop_repeats_and_placeholders_but_keep_a_codes_only_point(archive):
    pts = gp.points(gp.read_rows(archive))
    assert _codes(pts).count(("DE", "10117")) == 1  # an exact repeat
    # Paris's centre carries three codes beside their own points: a placeholder, dropped
    paris = [r for r in pts if r.country == "FR"]
    assert [(r.code, r.place) for r in paris] == [
        ("75007", "Paris 07"),
        ("75001", "Paris 01"),
        ("75008", "Paris 08"),
    ]
    # a code with several places keeps a point at each
    assert [r.place for r in pts if r.code == "2000"] == ["Sydney", "The Rocks"]


def test_reach_is_per_country_from_point_spacing_within_bounds(archive):
    pts = gp.points(gp.read_rows(archive))
    reach = gp.reaches(pts)
    assert set(reach) == {r.country for r in pts}
    assert all(gp.const.REACH_MIN_KM <= km <= gp.const.REACH_MAX_KM for km in reach.values())
    assert reach["AU"] == pytest.approx(2 * 1.09, rel=0.02)  # two points 1.09 km apart
    assert reach["PN"] == gp.const.REACH_MAX_KM  # a single point: the ceiling


def test_reach_scales_with_spacing_between_a_floor_and_a_ceiling():
    def reach(step_deg):
        rows = [gp.Row("XX", str(i), "", 10.0, 10.0 + step_deg * i) for i in range(20)]
        return gp.reaches(rows)["XX"]

    assert reach(0.05) == pytest.approx(2 * 5.47, rel=0.02)  # 0.05° of longitude at 10° N: 5.47 km
    assert reach(0.001) == gp.const.REACH_MIN_KM
    assert reach(1.0) == gp.const.REACH_MAX_KM


def test_layer_has_one_named_primary_row_per_code_and_secondary_points(archive):
    pts = gp.points(gp.read_rows(archive))
    layer = gp.postal_layer(pts, gp.reaches(pts))
    c = layer.columns
    assert layer.name == "postal" and layer.kind == "point" and layer.sources == ("geonames",)
    sydney = [i for i, cc in enumerate(c["country"]) if cc == "AU"]
    assert [c["id"][i] for i in sydney] == ["postal:AU:2000", "postal:AU:2000:2"]
    assert [c["secondary"][i] for i in sydney] == [False, True]
    assert [c["place"][i] for i in sydney] == ["Sydney", "The Rocks"]
    assert len(set(c["id"])) == len(c["id"])
    i = c["id"].index("postal:CZ:10000")  # ids without spaces
    assert c["name"][i] == "100 00" and c["codes"][i] == "100 00|10000"
    i = c["id"].index("postal:JP:1000005")
    assert c["codes"][i] == "100-0005|1000005"
    i = c["id"].index("postal:FR:75007")
    assert c["country"][i] == "FR" and "admin1" not in c  # Result.admin1 names the region already
    assert c["reach_km"][i] == math.ceil(gp.reaches(pts)["FR"])  # whole km, rounded up
    assert np.allclose(layer.lat[i], 48.8565) and np.allclose(layer.lon[i], 2.321)
    assert layer.types["reach_km"] == "u1" and layer.types["secondary"] == "bool"
