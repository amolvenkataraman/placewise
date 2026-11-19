"""Cards, park labels and generic park names on the real packs: public places only.

Skipped when a pack isn't built.
"""

import numpy as np
import pytest
from e2e_kit import geocoder, us_parks

import placewise.model as model
from placewise.engine._nearby.parks import generic_name
from placewise.model import PlaceKind

US = ("world", "usa", *us_parks())
CA = ("world", "can", "can-parks")


@pytest.mark.parametrize(
    ("packs", "point", "label"),
    [
        (US, (37.7284, -119.6115), "Yosemite Valley, Yosemite National Park"),
        (CA, (51.4254, -116.1773), "Lake Louise, Banff National Park"),
    ],
)
def test_park_labels(packs, point, label):
    assert geocoder(*packs).lookup(*point).label == label


def test_local_parks_and_water_keep_their_labels():
    r = geocoder(*US).lookup(40.7829, -73.9654)  # Central Park, a local park: the plain label
    assert "Central Park" in [p.name for p in r.within]
    assert "Central Park" not in r.label and r.label.endswith(", United States")


def test_cards_fit_and_round_trip():
    geo = geocoder(*US)
    namespace = {name: getattr(model, name) for name in model.__all__}
    for point in [(37.7284, -119.6115), (40.7829, -73.9654), (36.1147, -115.1728)]:
        r = geo.lookup(*point)
        card = str(r)
        assert card.splitlines()[0].startswith(r.label) and max(map(len, card.splitlines())) <= 100
        assert eval(repr(r), namespace) == r  # our own repr
        assert "<table" in r._repr_html_()


def test_no_generic_park_names_anywhere():
    """Old packs still have "Unknown Park" rows (the runtime guard skips them); new ones have none."""
    geo = geocoder(*US)
    pack = next(p for p in geo.packs if p.name == "usa-parks")
    lats, lons = (
        list(np.random.default_rng(7).uniform(25, 49, 500)),
        list(np.random.default_rng(8).uniform(-124, -67, 500)),
    )
    for layer in pack.layers.values():
        if layer.kind != "polygon":
            continue
        rows = [i for i, n in enumerate(layer.column("name").tolist()) if generic_name(n)][:40]
        for row in rows:  # the middle of a generic parcel's box: usually inside it
            box = layer.bbox(row)
            lats.append((box.south + box.north) / 2)
            lons.append((box.west + box.east) / 2)
    for r in geo.lookup_many(lats, lons):
        parks = [*r.within, *(n.place for n in r.near if n.place.kind == PlaceKind.PARK)]
        assert not [p.name for p in parks if generic_name(p.name)]
    for text in ("Open Space", "Unknown Park"):
        found = geo.find(text, limit=20)  # typo matches ("Oipen Space") are fine, the names aren't
        assert not [
            e.place.name for e in found if e.place.kind == PlaceKind.PARK and generic_name(e.place.name)
        ]
