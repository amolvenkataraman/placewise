"""COD-AB country packs (packbuild/codab.py) over public landmarks: what each answers now. Each test
skips when its pack isn't built (uv run python -m packbuild.codab <iso3>)."""

import pytest
from e2e_kit import geocoder


def names(r):
    return {
        f: (getattr(r, f).name if getattr(r, f) is not None else None)
        for f in ("sublocality", "locality", "city", "admin2", "admin1", "country")
    }


def look(pack, lat, lon):
    return geocoder("world", pack).lookup(lat, lon)


# -- Sri Lanka --------------------------------------------------------------------------------------


def test_colombo_fort():
    r = look("lka", 6.9344, 79.8428)
    assert names(r) == {
        "sublocality": "Fort", "locality": "Colombo", "city": "Colombo", "admin2": "Colombo",
        "admin1": "Western Province", "country": "Sri Lanka",
    }  # fmt: skip
    assert r.label == "Colombo, Western Province, Sri Lanka"
    assert r.admin1.id == "codab:LK1" and r.sources["sublocality"] == "lka/admin4:polygon"


def test_kandy_temple_of_the_tooth():
    r = look("lka", 7.2936, 80.6413)
    assert (r.locality.name, r.admin2.name, r.admin1.name) == ("Kandy", "Kandy", "Central Province")
    # the Grama Niladhari division is Mahanuwara, Kandy's Sinhala name: no alias table yet
    assert r.sublocality.name == "Mahanuwara"


# -- Nepal ------------------------------------------------------------------------------------------


def test_kathmandu_durbar_square():
    r = look("npl", 27.7046, 85.3074)
    assert names(r) == {
        "sublocality": None, "locality": "Kathmandu", "city": "Kathmandu", "admin2": "Kathmandu",
        "admin1": "Bagmati", "country": "Nepal",
    }  # fmt: skip
    assert r.admin1.id == "codab:NP03"  # the province, not the pre-2015 zone of the same name
    assert r.sources["locality"] == "npl/admin3:polygon"


def test_pokhara_phewa_lake():
    r = look("npl", 28.2096, 83.9586)
    assert (r.locality.name, r.admin2.name, r.admin1.name) == ("Pokhara", "Kaski", "Gandaki")
    assert r.label == "Pokhara, Gandaki, Nepal"


def test_patan_is_in_lalitpur_metropolitan_city():
    r = look("npl", 27.6727, 85.3240)
    assert (r.locality.name, r.city.name, r.admin2.name) == ("Lalitpur", "Pātan", "Lalitpur")


def test_kalapani_is_india_and_not_in_the_nepal_pack():
    from e2e_kit import require_packs

    from placewise.packs import open_pack

    (npl,) = require_packs("npl")
    pack = open_pack(npl)
    for layer in ("admin1", "admin2", "admin3"):
        assert int(pack[layer].query([30.205], [80.99])[0]) == -1
    r = look("npl", 30.205, 80.99)
    assert (r.country.name, r.admin1.name, r.locality) == ("India", "Uttarakhand", None)


# -- Bangladesh -------------------------------------------------------------------------------------


def test_dhaka_shaheed_minar():
    r = look("bgd", 23.7271, 90.3966)
    assert (r.locality.name, r.admin2.name, r.admin1.name) == ("Dhaka", "Dhaka", "Dhaka")
    assert r.admin1.id == "iso:BD-C"  # the world's Dhaka Division agrees: kept, with its ISO code


def test_coxs_bazar_beach():
    r = look("bgd", 21.4272, 91.9702)
    assert (r.admin2.name, r.admin1.name) == ("Cox's Bazar", "Chattogram")
    assert r.admin1.id == "codab:BD20"  # Natural Earth's is "Chittagong": the COD-AB name answers


# -- Thailand ---------------------------------------------------------------------------------------


def test_bangkok_grand_palace():
    r = look("tha", 13.7500, 100.4913)
    assert (r.locality.name, r.admin2.name, r.admin1.name) == ("Bangkok", "Phra Nakhon", "Bangkok")
    assert r.sublocality.name == "Phraborom Maharatchawang"


def test_chiang_mai_old_city():
    r = look("tha", 18.7883, 98.9853)
    want = ("Chiang Mai", "Mueang Chiang Mai", "Chiang Mai")
    assert (r.locality.name, r.admin2.name, r.admin1.name) == want
    assert r.sublocality.name == "Phra Sing"


# -- the rest ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("pack", "lat", "lon", "admin2", "admin1"),
    [
        ("vnm", 21.0287, 105.8524, None, "Ha Noi"),  # Hoan Kiem Lake; ADM1 only, the 2025 provinces
        ("vnm", 10.7725, 106.6980, None, "Ho Chi Minh city"),  # Ben Thanh market
        ("are", 25.1972, 55.2744, None, "Dubai"),  # Burj Khalifa
        ("mex", 19.4326, -99.1332, "Cuauhtémoc", "Distrito Federal"),  # Zocalo; the world's admin1 kept
        ("zaf", -33.9486, 18.4026, "City of Cape Town", "Western Cape"),  # Table Mountain cableway
        ("ken", -1.2884, 36.8233, "Starehe", "Nairobi"),  # KICC
        ("egy", 29.9792, 31.1342, "Zemam Out", "Giza"),  # the Giza pyramids
        ("tur", 41.0086, 28.9802, "Fatih", "Istanbul"),  # Hagia Sophia
    ],
)
def test_landmarks(pack, lat, lon, admin2, admin1):
    r = look(pack, lat, lon)
    assert (r.admin2.name if r.admin2 else None, r.admin1.name) == (admin2, admin1)
