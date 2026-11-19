"""Town and city outlines (the world-towns pack) over the real world pack: public places outside
the US, Canada and India, and proof that answers there never change."""

import dataclasses

import numpy as np
import pytest
from e2e_kit import geocoder, optional, require_packs

from placewise.model import Relation

TOWNS = "world-towns/towns:polygon"
SCORE = "world/cities:score"


@pytest.fixture(scope="module")
def geo():
    return geocoder("world", "world-towns")


def names(r):
    return r.locality.name, r.city.name


def test_la_defense_is_in_paris(geo):
    r = geo.lookup(48.892, 2.236)  # La Defense: the commune stays the locality, Paris is the city
    assert names(r) == ("Courbevoie", "Paris")
    assert r.sources["city"] == TOWNS and r.matches["city"].relation == Relation.WITHIN
    assert r.sources["locality"] == SCORE
    assert r.label == "Courbevoie, Hauts-de-Seine, France"
    assert "Paris" not in [n.place.name for n in r.near]


@pytest.mark.parametrize(
    ("point", "city", "country"),
    [
        ((48.8606, 2.3376), "Paris", "FR"),  # the Louvre
        ((45.7578, 4.8320), "Lyon", "FR"),  # Place Bellecour
        ((-1.2864, 36.8172), "Nairobi", "KE"),  # the CBD
        ((43.7731, 11.2560), "Florence", "IT"),  # the Duomo
        ((35.6812, 139.7671), "Tokyo", "JP"),  # Tokyo Station
        ((35.6896, 139.7006), "Tokyo", "JP"),  # Shinjuku
    ],
)
def test_city_centres_are_within_their_outline(geo, point, city, country):
    r = geo.lookup(*point)
    assert names(r) == (city, city)
    assert r.sources["city"] == r.sources["locality"] == TOWNS
    assert r.matches["locality"].relation == Relation.WITHIN
    assert r.country.codes["iso2"] == country


def test_yokohama_stays_yokohama_inside_the_tokyo_outline(geo):
    # one GHS-SMOD urban centre runs from Tokyo through Kawasaki to Yokohama (33.5M people); the
    # big cities inside it keep their own name as the city
    assert names(geo.lookup(35.4658, 139.6223)) == ("Yokohama", "Yokohama")  # Yokohama Station
    assert names(geo.lookup(35.5313, 139.6969)) == ("Kawasaki", "Kawasaki")  # Kawasaki Station
    tokyo = geo.lookup(35.5850, 139.6690)  # the Tokyo bank of the Tama, across from Kawasaki
    assert names(tokyo) == ("Tokyo", "Tokyo") and tokyo.sources["city"] == TOWNS


def test_a_village_near_florence_is_not_florence(geo):
    plain = geocoder("world")
    point = (43.7246, 11.2856)  # Ponte a Ema, a village outside Florence's urban centre
    assert names(plain.lookup(*point)) == ("Florence", "Florence")  # the bigger city scored higher
    r = geo.lookup(*point)
    assert names(r) == ("Ponte a Ema", "Ponte a Ema") and r.sources["locality"] == TOWNS
    assert names(geo.lookup(43.7731, 11.2560)) == ("Florence", "Florence")  # the Duomo


def test_a_suburb_town_rolls_up_into_its_city(geo):
    r = geo.lookup(48.8049, 2.1204)  # Versailles, inside Paris' urban centre
    assert names(r) == ("Versailles", "Paris")


def test_tijuana_is_cut_from_san_diego(geo):
    r = geo.lookup(32.5149, -117.0382)
    assert names(r) == ("Tijuana", "Tijuana") and r.sources["city"] == TOWNS


def points_in(boxes, n=1500, seed=4):
    rng = np.random.default_rng(seed)
    lat, lon = [], []
    for south, west, north, east in boxes:
        lat.append(rng.uniform(south, north, n))
        lon.append(rng.uniform(west, east, n))
    return np.concatenate(lat), np.concatenate(lon)


# metros of the US, Canada and India (and their borders), where outlines would otherwise apply
COUNTRY_PACK_BOXES = [
    (40.5, -74.3, 41.0, -73.7),  # New York
    (33.7, -118.5, 34.3, -117.9),  # Los Angeles
    (32.4, -117.3, 32.8, -116.8),  # San Diego and Tijuana
    (42.2, -83.3, 42.45, -82.9),  # Detroit and Windsor
    (43.5, -79.7, 43.9, -79.1),  # Toronto
    (45.4, -73.9, 45.7, -73.4),  # Montreal
    (28.4, 76.8, 28.9, 77.4),  # Delhi, Gurugram, Noida
    (12.8, 77.4, 13.2, 77.8),  # Bengaluru
    (18.9, 72.8, 19.3, 73.1),  # Mumbai
]


def strip(r):
    return dataclasses.replace(r, data_version="")


@pytest.mark.parametrize("country_packs", [False, True])
def test_us_canada_india_answers_never_change(country_packs):
    require_packs("world-towns")
    names_ = ("world", *(optional("usa", "usa-zip", "can", "ind") if country_packs else ()))
    lat, lon = points_in(COUNTRY_PACK_BOXES)
    before = geocoder(*names_).lookup_many(lat, lon)
    after = geocoder(*names_, "world-towns").lookup_many(lat, lon)
    home = [
        i
        for i, r in enumerate(before)
        if r.country is not None and r.country.codes.get("iso2") in {"US", "CA", "IN"}
    ]
    assert len(home) > 8_000
    assert [strip(after[i]) for i in home] == [strip(before[i]) for i in home]
    # across the borders (Tijuana, Windsor's neighbours are Canadian) the outlines do apply
    seen = set(home)
    abroad = [i for i in range(len(before)) if i not in seen and before[i].country is not None]
    assert any(after[i].sources.get("city") == TOWNS for i in abroad)
