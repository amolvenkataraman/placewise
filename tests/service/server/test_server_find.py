"""The HTTP API's forward search over real sockets: /v1/find (GET and POST) and /v1/get."""

import pytest
from server_kit import call

# -- forward search ----------------------------------------------------------------------------------


def test_get_find_passes_the_context(serve, fake):
    reply = call(
        serve(), "GET", "/v1/find?q=tower&limit=3&country=US,CA&near=43.6,-79.4&kinds=landmark&strict=0"
    )
    assert reply.status == 200
    assert [e["place"]["id"] for e in reply.json["results"]] == ["test:cn_tower", "test:eiffel"]
    kind, _, options = fake.calls[-1]
    assert kind == "find" and options["limit"] == 3 and options["country"] == ["US", "CA"]
    assert (
        options["near"] == (43.6, -79.4) and options["kinds"] == ["landmark"] and options["strict"] is False
    )


def test_post_find_takes_json(serve, fake):
    body = {"q": "opera", "near": [-33.8, 151.2], "radius_km": 50, "bbox": [-34, 151, -33, 152]}
    reply = call(serve(), "POST", "/v1/find", json_body=body)
    assert reply.status == 200 and reply.json["results"][0]["place"]["id"] == "test:opera_house"
    options = fake.calls[-1][2]
    assert options["radius_km"] == 50 and options["bbox"] == (-34, 151, -33, 152)


def test_find_says_how_sure_each_context_is(serve, fake):
    opera = call(serve(), "GET", "/v1/find?q=opera").json["results"][0]
    assert opera["context_certain"] is False
    assert opera["context_matches"]["country"] == {"relation": "offshore", "distance_km": 0.2}
    tower = call(serve(), "GET", "/v1/find?q=tower").json["results"][0]
    assert tower["context_certain"] is True and tower["context_matches"]["city"]["relation"] == "near"


@pytest.mark.parametrize(
    "path",
    [
        "/v1/find",
        "/v1/find?q=",
        "/v1/find?q=x&limit=0",
        "/v1/find?q=x&limit=500",
        "/v1/find?q=x&near=1",
        "/v1/find?q=x&near=91,0",
        "/v1/find?q=x&prefix=maybe",
        "/v1/find?q=x&color=red",
        "/v1/find?q=" + "x" * 300,
        "/v1/get",
    ],
)
def test_find_and_get_reject_bad_input(serve, path):
    reply = call(serve(), "GET", path)
    assert reply.status == 400 and reply.error_code == "bad_request"


def test_get_by_id_and_unknown_id(serve):
    server = serve()
    reply = call(server, "GET", "/v1/get?id=test:eiffel")
    assert reply.status == 200 and reply.json["place"]["name"] == "Eiffel Tower"
    missing = call(server, "GET", "/v1/get?id=test:nowhere")
    assert missing.status == 404 and missing.error_code == "not_found"
