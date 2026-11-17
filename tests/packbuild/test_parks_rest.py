"""The ArcGIS query pager the park sources share (packbuild.sources.parks._rest), on a fake service."""

import json

import pytest

from packbuild.sources.parks import _rest

LAYER = "https://example.org/arcgis/rest/services/Parks/FeatureServer/0"


def feature(oid):
    ring = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]
    return {"attributes": {"OBJECTID": oid, "NAME": f"Park {oid}"}, "geometry": {"rings": [ring]}}


class FakeService:
    """Answers id and feature queries; `fails` maps an object id to the requests that fail for it."""

    def __init__(self, ids, fails=None, refuse_generalised=()):
        self.ids, self.fails, self.refuse = ids, dict(fails or {}), set(refuse_generalised)
        self.calls = []

    def __call__(self, url, params):
        self.calls.append(params)
        assert url == f"{LAYER}/query"
        if params.get("returnIdsOnly") == "true":
            assert params["where"] == "TYPE='NP'"
            return json.dumps({"objectIdFieldName": "OBJECTID", "objectIds": self.ids[::-1]}).encode()
        batch = [int(i) for i in params["objectIds"].split(",")]
        if "maxAllowableOffset" in params and self.refuse & set(batch):
            return json.dumps({"error": {"code": 400, "message": "Cannot perform query."}}).encode()
        if len(batch) > 2 and any(self.fails.get(i) for i in batch):
            return json.dumps({"error": {"code": 504, "message": "timeout"}}).encode()
        return json.dumps({"features": [feature(i) for i in batch]}).encode()


def test_pages_hold_every_matching_feature_in_id_order(tmp_path):
    service = FakeService([5, 1, 3, 2, 4])
    folder = _rest.fetch_query(LAYER, "TYPE='NP'", tmp_path, "parks", out_sr=3978, offset=10, precision=0,
                               page_size=2, post=service)  # fmt: skip
    assert sorted(p.name for p in folder.iterdir()) == ["page-0000.json", "page-0001.json", "page-0002.json"]
    rows = _rest.read_pages(folder)
    assert [a["OBJECTID"] for a, _ in rows] == [1, 2, 3, 4, 5]
    assert rows[0][1][0].shape == (5, 2)
    query = service.calls[1]
    assert (query["outSR"], query["maxAllowableOffset"], query["geometryPrecision"]) == ("3978", "10", "0")
    meta = json.loads((tmp_path / "parks.json").read_text())
    assert meta["features"] == 5 and meta["pages"] == 3 and meta["where"] == "TYPE='NP'"
    assert meta["ungeneralised"] == [] and len(meta["sha256"]) == 64
    # cached: asked once
    again = FakeService([])
    assert (
        _rest.fetch_query(LAYER, "TYPE='NP'", tmp_path, "parks", post=again) == folder and again.calls == []
    )


def test_a_refused_page_is_split_and_asked_again(tmp_path):
    service = FakeService(list(range(1, 7)), fails={4: True})
    folder = _rest.fetch_query(LAYER, "TYPE='NP'", tmp_path, "parks", page_size=6, post=service)
    assert [a["OBJECTID"] for a, _ in _rest.read_pages(folder)] == [1, 2, 3, 4, 5, 6]
    assert len(list(folder.iterdir())) == 3  # 6 -> 3 + 3 -> the half with 4 split again: 1 + 2


def test_a_feature_the_service_cannot_generalise_comes_at_full_resolution(tmp_path):
    service = FakeService([1, 2, 3], refuse_generalised={2})
    folder = _rest.fetch_query(LAYER, "TYPE='NP'", tmp_path, "parks", offset=10, page_size=3, post=service)
    assert [a["OBJECTID"] for a, _ in _rest.read_pages(folder)] == [1, 2, 3]
    assert _rest.ungeneralised(folder) == {2}
    asked = [c for c in service.calls if c.get("objectIds") == "2"]
    assert ["maxAllowableOffset" in c for c in asked] == [True, False]


def test_a_feature_refused_outright_fails_and_leaves_no_cache(tmp_path):
    service = FakeService([1, 2], refuse_generalised={2})
    with pytest.raises(RuntimeError, match="object id 2"):
        _rest.fetch_query(LAYER, "TYPE='NP'", tmp_path, "parks", offset=None, page_size=2,
                          post=lambda u, p: service(u, {**p, "maxAllowableOffset": "1"}))  # fmt: skip
    assert list(tmp_path.iterdir()) == []
