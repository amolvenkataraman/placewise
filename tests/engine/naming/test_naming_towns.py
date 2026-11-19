"""The world-towns pack never changes an answer in the US, Canada or India (their packs name places),
even with outlines drawn over them, with or without the country packs (naming_kit's world)."""

import dataclasses

import numpy as np
import pytest
from naming_kit import CREATED, VERSION, box

from placewise.engine import Geocoder
from placewise.packs import LayerData, write_pack

ROWS = [  # box, id, name, geonames, class, country
    ((10.5, -150.0, 11.0, -149.5), "ghs:US:103", "New York City", "geonames:103", "centre", "US"),
    ((10.5, -149.0, 11.0, -148.5), "ghs:CA:206", "Toronto", "geonames:206", "centre", "CA"),
    ((10.0, -148.0, 10.5, -147.5), "ghs:IN:303", "Delhi", "geonames:303", "centre", "IN"),
]


@pytest.fixture(scope="module")
def towns(tmp_path_factory):
    columns = {
        c: [r[1 + i] for r in ROWS] for i, c in enumerate(("id", "name", "geonames", "class", "country"))
    }
    layer = LayerData("towns", "polygon", columns, ("ghsl",), features=[box(*r[0]) for r in ROWS])
    out = tmp_path_factory.mktemp("towns")
    return write_pack(out, "world-towns", VERSION, [layer], created=CREATED, about={"kind": "towns"})


def points():
    rng = np.random.default_rng(11)
    return rng.uniform(10.0, 11.0, 400), rng.uniform(-150.0, -147.0, 400)


def same(a, b):
    return [dataclasses.replace(r, data_version="") for r in a] == [
        dataclasses.replace(r, data_version="") for r in b
    ]


def test_with_the_country_packs(packs, towns, geo):
    lat, lon = points()
    with_towns = Geocoder(packs=[*packs, towns])
    assert with_towns.towns  # the layer is read ...
    assert same(with_towns.lookup_many(lat, lon), geo.lookup_many(lat, lon))  # ... and never used here


def test_without_the_country_packs(packs, towns, world_only):
    lat, lon = points()
    assert same(Geocoder(packs=[packs[0], towns]).lookup_many(lat, lon), world_only.lookup_many(lat, lon))
