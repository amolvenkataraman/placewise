"""The COD-AB naming rule (engine/naming/codab.py) over synthetic packs (codab_kit)."""

import pytest
from codab_kit import write_all

from placewise.engine import Geocoder


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    return write_all(tmp_path_factory.mktemp("codab"))


@pytest.fixture(scope="module")
def geo(packs):
    return Geocoder(packs=list(packs))


def names(r):
    return {f: getattr(r, f).name if getattr(r, f) is not None else None
            for f in ("sublocality", "locality", "city", "admin2", "admin1", "country")}  # fmt: skip


def test_nepal_locality_is_the_local_level_and_admin1_the_province(geo):
    r = geo.lookup(20.755, 160.255)
    assert names(r) == {
        "sublocality": "Thamel", "locality": "Kathmandu", "city": "Kathmandu", "admin2": "Kathmandu",
        "admin1": "Bagmati", "country": "Nepal",
    }  # fmt: skip
    # the world's "Bagmati" is the old zone: Nepal's world_admin1 is off, so the province answers
    assert r.admin1.id == "codab:NP03" and r.admin1.codes == {"pcode": "NP03", "country": "NP"}
    assert r.locality.id == "codab:NP0327301" and r.locality.kind.value == "locality"
    assert r.sources["locality"] == "npl/admin3:polygon"
    assert r.sources["admin2"] == "npl/admin2:parent" and r.sources["admin1"] == "npl/admin1:parent"
    assert r.sources["city"] == "world/cities:score" and r.sources["sublocality"] == "world/cities:inside"
    assert r.label == "Kathmandu, Bagmati, Nepal"


def test_the_city_stays_the_geonames_answer(geo):
    r = geo.lookup(20.74, 160.74)
    assert (r.locality.name, r.city.name, r.sublocality) == ("Lalitpur", "Patan", None)
    assert r.label == "Lalitpur, Bagmati, Nepal"


def test_a_point_just_outside_every_unit_snaps_to_the_nearest(geo):
    r = geo.lookup(20.5, 160.995)  # in the world's Nepal, ~500 m east of Lalitpur's edge
    assert r.locality.name == "Lalitpur" and r.sources["locality"] == "npl/admin3:nearest"


def test_sri_lanka_province_district_and_grama_niladhari_division(geo):
    r = geo.lookup(20.38, 161.5)
    assert names(r) == {
        "sublocality": "Fort", "locality": "Colombo", "city": "Colombo", "admin2": "Colombo",
        "admin1": "Western Province", "country": "Sri Lanka",
    }  # fmt: skip
    assert r.sources["sublocality"] == "lka/admin4:polygon" and r.sources["locality"] == "world/cities:score"
    assert geo.lookup(20.5, 161.5).sublocality is None  # the division named like the city
    assert geo.lookup(20.62, 161.5).sublocality.name == "Pettah"


def test_a_matching_world_admin1_is_kept_else_the_pack_names_it(geo):
    dhaka = geo.lookup(20.75, 162.5)
    assert dhaka.admin1.id == "iso:BD-C" and dhaka.sources["admin1"] == "bgd/admin3:state"
    khulna = geo.lookup(20.25, 162.5)  # the world's is "Khulna Division": no match by name
    assert khulna.admin1.id == "codab:BD40" and khulna.admin1.name == "Khulna"
    assert khulna.admin2.name == "Khulna" and khulna.locality.name == "Khulna"  # GeoNames
    assert dhaka.locality.name == "Dhaka" and dhaka.sublocality is None


def test_lookup_many_agrees_with_lookup(geo):
    pts = [(20.755, 160.255), (20.38, 161.5), (20.25, 162.5), (20.74, 160.74)]
    many = geo.lookup_many([p[0] for p in pts], [p[1] for p in pts])
    assert [r.label for r in many] == [geo.lookup(*p).label for p in pts]


def test_without_the_pack_the_world_answers(packs):
    world = Geocoder(packs=[packs[0]])
    r = world.lookup(20.74, 160.24)
    assert (r.admin1.id, r.locality.name, r.admin2) == ("iso:NP-BA", "Kathmandu", None)


def test_only_configured_countries_are_codab_packs(packs, tmp_path):
    from placewise.engine.naming.codab import Codab
    from placewise.packs import open_pack

    assert all(Codab.accepts(open_pack(p)) for p in packs[1:])
    assert not Codab.accepts(open_pack(packs[0]))  # "world" has an admin1 layer too
