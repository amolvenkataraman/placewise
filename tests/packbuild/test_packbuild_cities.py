"""packbuild.cities: GeoNames cities and datasets/cities/aliases.json -> generated modules."""

import pytest
from datasets_kit import needs_datasets

from packbuild import cities
from packbuild.fetch import DEFAULT_CACHE
from packbuild.sources.geonames import GEONAME_FIELDS

CACHED = DEFAULT_CACHE / "cities1000" / "cities1000.txt"
ADMIN1 = DEFAULT_CACHE / "admin1CodesASCII.txt"


@needs_datasets
def test_city_aliases_module_matches_the_dataset():
    path = cities.PACKAGE / "city_aliases.py"
    assert path.read_text(encoding="utf-8") == cities.render_aliases(cities.load_aliases()), (
        "constants/countries/city_aliases.py is out of date: run python -m packbuild.cities"
    )


@pytest.mark.skipif(not (CACHED.exists() and ADMIN1.exists()), reason="GeoNames files not downloaded")
@needs_datasets
def test_city_modules_match_geonames():
    for path, text in cities.outputs(CACHED, ADMIN1).items():
        assert path.read_text(encoding="utf-8") == text, (
            f"{path} is out of date: run python -m packbuild.cities"
        )


def _row(gid, name, country, admin1, population, code="PPL", alternates=""):
    fields = dict.fromkeys(GEONAME_FIELDS, "")
    fields.update(
        geonameid=str(gid),
        name=name,
        asciiname=name,
        alternatenames=alternates,
        country_code=country,
        admin1_code=admin1,
        population=str(population),
        feature_code=code,
        feature_class="P",
    )
    return "\t".join(fields[f] for f in GEONAME_FIELDS)


@pytest.fixture
def geonames(tmp_path):
    rows = [
        _row(1, "Toronto", "CA", "08", 2_794_356),
        _row(2, "Smallton", "CA", "08", 5_000),
        _row(3, "Iqaluit", "CA", "14", 7_740, code="PPLA"),
        _row(4, "Springfield", "US", "IL", 114_394, code="PPLA"),
        _row(5, "Paris", "FR", "11", 2_138_551),
        _row(6, "Bengaluru", "IN", "19", 8_443_675, alternates="Bangalore"),
    ]
    cities_path = tmp_path / "cities1000.txt"
    cities_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    admin1 = tmp_path / "admin1CodesASCII.txt"
    admin1.write_text(
        "CA.08\tOntario\tOntario\t6093943\nCA.14\tNunavut\tNunavut\t6091732\nIN.19\tKarnataka\tKarnataka\t1267701\n"
    )
    return cities_path, admin1


def test_read_cities_keeps_big_places_and_seats(geonames):
    found = cities.read_cities(*geonames)
    assert [(n, a, p) for n, a, p, _ in found["CA"]] == [
        ("Toronto", "ON", 2_794_356),
        ("Iqaluit", "NU", 7_740),
    ]
    assert [(n, a) for n, a, _, _ in found["US"]] == [("Springfield", "IL")]
    assert [(n, a) for n, a, _, _ in found["IN"]] == [("Bengaluru", "KA")]
    assert "FR" not in found


def test_render_cities(geonames):
    text = cities.render_cities("CA", cities.read_cities(*geonames)["CA"])
    assert text.startswith(
        '"""GENERATED from GeoNames cities1000 (CC BY 4.0) by packbuild.cities; do not edit.'
    )
    namespace = {}
    exec(compile(text, "cities.py", "exec"), namespace)
    assert namespace["CITIES"] == (("Toronto", "ON", 2_794_356), ("Iqaluit", "NU", 7_740))


def test_aliases_must_name_a_geonames_city(geonames):
    cities.check_aliases({"YYZ": {"city": "Toronto", "country": "CA", "admin1": "ON"}}, geonames[0])
    cities.check_aliases(
        {"Bangalore": {"city": "Bangalore", "country": "IN"}}, geonames[0]
    )  # an alternate name
    with pytest.raises(ValueError, match="Atlantis"):
        cities.check_aliases({"ATL": {"city": "Atlantis", "country": "CA"}}, geonames[0])


def test_unmapped_admin1_is_an_error(geonames, tmp_path):
    cities_path, _ = geonames
    empty = tmp_path / "empty_admin1.txt"
    empty.write_text("")
    with pytest.raises(ValueError, match="no ISO code"):
        cities.read_cities(cities_path, empty)
