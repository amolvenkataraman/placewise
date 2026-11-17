"""CGNDB populated places (Natural Resources Canada, OGL-Canada 2.0) as the Canada pack's
`populated_places` point layer."""

import zipfile

import numpy as np
import pytest
from cgndb_fixtures import write_archive

from packbuild.sources.can import cgndb


@pytest.fixture
def archive(tmp_path):
    return write_archive(tmp_path)


def test_populated_places_only_without_railway_points_or_post_offices(archive):
    layer = cgndb.populated_places(archive)
    assert (layer.name, layer.kind, layer.sources) == ("populated_places", "point", (cgndb.SOURCE,))
    cols = layer.columns
    assert cols["id"] == ["cgndb:IACFT", "cgndb:JAVJO", "cgndb:FDQBU", "cgndb:FEBVQ", "cgndb:EDLAA"]
    assert cols["name"][0] == "Lake Louise" and cols["generic"][0] == "Hamlet"
    assert cols["province"] == ["AB", "BC", "ON", "ON", "QC"]
    assert list(cols["scale"]) == [1_200_000, 2_000_000, 1_200_000, 145_000, 85_000]
    assert layer.types["scale"] == "i8"
    np.testing.assert_allclose(layer.lat[:2], [51.4252778, 51.3955556])
    np.testing.assert_allclose(layer.lon[:2], [-116.1805556, -116.4880556])


def test_a_csv_with_other_columns_is_refused(tmp_path):
    path = tmp_path / "cgn.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("cgn.csv", "Name,Lat\nX,1\n")
    with pytest.raises(ValueError, match="Generic Category"):
        cgndb.populated_places(path)


def test_writes_a_pack_layer(archive, tmp_path):
    from placewise.packs import open_pack, write_pack

    path = write_pack(tmp_path / "out", "can", "2026.11", [cgndb.populated_places(archive)])
    layer = open_pack(path, verify=True)["populated_places"]
    i, km = layer.nearest(51.4254, -116.1773)
    assert layer.row(int(i))["name"] == "Lake Louise" and float(km) < 0.3
