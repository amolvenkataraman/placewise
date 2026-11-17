"""placewise.overrides._index: the rules apply runs for an answer give the same answer as running
every rule, in order."""

import json
import math
import random

import pytest
from overrides_kit import (
    CALIFORNIA,
    CANADA,
    KARIYA_PARK,
    LAKE_ONTARIO,
    MISSISSAUGA,
    ONTARIO,
    PEARSON,
    PEEL,
    TORONTO,
    USA,
    mississauga_result,
    oakland_result,
    toronto_result,
)

from placewise.model import Layer, Nearby, Result
from placewise.overrides import OverrideEngine, _index
from placewise.overrides._index import introduced_ids

PLACES = (MISSISSAUGA, TORONTO, PEEL, KARIYA_PARK, LAKE_ONTARIO, PEARSON)
CENTRE = (43.6, -79.5)


def _point(rng, spread=0.6):
    return round(CENTRE[0] + rng.uniform(-spread, spread), 5), round(
        CENTRE[1] + rng.uniform(-spread, spread), 5
    )


def _area(rng, folder, kind=None):
    lat, lon = _point(rng)
    kind = rng.randrange(6) if kind is None else kind
    if kind == 0:
        return {"point": {"lat": lat, "lon": lon}, "km": rng.uniform(0.5, 25)}
    if kind == 1:
        d = rng.uniform(0.01, 0.3)
        return {"bbox": {"south": lat - d, "west": lon - d, "north": lat + d, "east": lon + d}}
    if kind == 2:
        d = rng.uniform(0.05, 0.3)
        ring = [[lon - d, lat - d], [lon + d, lat], [lon, lat + d], [lon - d, lat - d]]
        name = f"area{rng.randrange(10**9)}.geojson"
        (folder / name).write_text(json.dumps({"type": "Polygon", "coordinates": [ring]}))
        return {"geojson": name}
    if kind == 3:
        return {"country": rng.choice(("CA", "US", "ca"))}
    if kind == 4:
        return {"place": rng.choice(PLACES).id}
    return {"country": "CA"}


def _rules(rng, folder, ids, n):
    doc = {t: [] for t in ("label", "city", "add", "rename", "hide", "region", "tune")}
    for i in range(n):
        lat, lon = _point(rng)
        what = rng.randrange(9)
        target = rng.choice([*ids, *(p.id for p in PLACES)])
        if what == 0:
            field = rng.choice(("city", "locality", "region", "admin2", "label"))
            doc["label"].append({"within": _area(rng, folder), "fields": {field: f"Label {i}"}})
        elif what == 1:
            doc["city"].append({"within": _area(rng, folder), "city": f"City {i}"})
        elif what == 2:
            doc["city"].append({"locality": target, "city": f"City {i}"})
        elif what == 3:
            add = {"kind": rng.choice(("landmark", "region", "airport", "water")), "name": f"Place {i}"}
            add.update(point={"lat": lat, "lon": lon}, radius_m=rng.uniform(100, 30000))
            if rng.random() < 0.5:
                add["id"] = rng.choice((f"test:added/{rng.randrange(20)}", target))
            if rng.random() < 0.2:
                add["within"] = _area(rng, folder)
            doc["add"].append(add)
        elif what == 4:
            doc["rename"].append({"id": target, "name": f"Renamed {i}", "aliases": [f"Alias {i}"]})
        elif what == 5:
            doc["hide"].append({"id": target})
        elif what in (6, 7):
            region = {"id": rng.choice((f"test:region/{rng.randrange(5)}", target)), "label": f"Region {i}"}
            choice = rng.randrange(4)
            if choice == 0:
                region["members"] = {"ca_cd": [rng.choice(("3521", "3520", "9999"))]}
            elif choice == 1:
                region["members"] = {"id": [target]}
            elif choice == 2:
                region["polygon"] = _area(rng, folder).get("geojson") or _area(rng, folder, kind=2)["geojson"]
            else:
                region["remove"] = True
            doc["region"].append(region)
        else:
            tune = (
                {"id": target} if rng.random() < 0.5 else {"kind": rng.choice(("airport", "park", "water"))}
            )
            tune.update(rng.choice(({"tier": rng.randrange(1, 4)}, {"near_km": rng.uniform(1, 10)})))
            doc["tune"].append(tune)
    return {k: v for k, v in doc.items() if v}


def _engine(rng, folder):
    repo = _rules(rng, folder, [], 40)
    first = OverrideEngine.from_documents([(Layer.REPO, repo, "repo:r.toml", folder)])
    ids = sorted({pid for rule in first.rules for pid in introduced_ids(rule)})  # later rules aim at them
    local = _rules(rng, folder, ids, 40)
    return OverrideEngine.from_documents(
        [(Layer.REPO, repo, "repo:r.toml", folder), (Layer.LOCAL, local, "local:l.toml", folder)]
    )


def _results(rng, n):
    out = []
    for _ in range(n):
        base = rng.choice((mississauga_result, toronto_result, oakland_result))()
        lat, lon = _point(rng, 0.8) if rng.random() < 0.9 else (base.lat, base.lon)
        near = tuple(Nearby(p, "near", rng.uniform(0, 12)) for p in rng.sample(PLACES, 2))
        country, admin1 = (CANADA, ONTARIO) if rng.random() < 0.8 else (USA, CALIFORNIA)
        out.append(Result(lat, lon, label=base.label, country=country, admin1=admin1, admin2=base.admin2,
                          city=base.city, locality=base.locality, regions=base.regions, within=base.within,
                          near=near, airport=base.airport))  # fmt: skip
    return out


def _apply_all(engine, result, relabel):
    """apply with every rule run: what the index must agree with."""
    index = _index.RuleIndex.__new__(_index.RuleIndex)
    real = engine._index
    everything = real._everything if real is not None else None
    try:
        engine._index = index
        index.followers = [()] * len(engine)
        index.candidates = lambda r, lat, lon: list(everything)
        return engine.apply(result, result.lat, result.lon, relabel=relabel)
    finally:
        engine._index = real


@pytest.mark.parametrize("seed", range(12))
def test_indexed_apply_matches_running_every_rule(tmp_path, seed):
    rng = random.Random(seed)
    folder = tmp_path / str(seed)
    folder.mkdir()
    engine = _engine(rng, folder)
    relabel = lambda r: f"{r.city.name if r.city else '?'} / {len(r.regions)}"  # noqa: E731
    results = _results(rng, 60)
    changed = 0
    for result in results:
        indexed = engine.apply(result, result.lat, result.lon, relabel=relabel)
        assert indexed == _apply_all(engine, result, relabel)
        changed += indexed != result
    assert changed > len(results) // 2


def test_an_area_past_the_antimeridian_or_near_a_pole_still_matches():
    rules = {
        "label": [
            {"within": {"point": {"lat": 0.0, "lon": 179.99}, "km": 20}, "fields": {"city": "Wrapped"}},
            {"within": {"point": {"lat": 89.99, "lon": 0.0}, "km": 5}, "fields": {"admin2": "Polar"}},
            {
                "within": {"bbox": {"south": -1, "west": 179, "north": 1, "east": -179}},
                "fields": {"region": "Box"},
            },
        ]
    }
    engine = OverrideEngine.from_documents([(Layer.LOCAL, rules, "local:l.toml")])
    east = engine.apply(Result(0.0, -179.95), 0.0, -179.95)
    assert east.city.name == "Wrapped" and [r.name for r in east.regions] == ["Box"]
    polar = engine.apply(Result(89.995, 120.0), 89.995, 120.0)
    assert polar.admin2.name == "Polar"


def test_a_missing_geojson_raises_where_it_did(tmp_path):
    rules = {"label": [{"within": {"geojson": "missing.geojson"}, "fields": {"city": "Never"}}]}
    engine = OverrideEngine.from_documents([(Layer.LOCAL, rules, "local:l.toml", tmp_path)])
    for _ in range(2):  # every answer, as before: the file may turn up later
        with pytest.raises(FileNotFoundError):
            engine.apply(toronto_result(), *CENTRE)


def _destination(lat, lon, bearing_deg, km):
    b, d = math.radians(bearing_deg), km / 6371.0088
    la1, lo1 = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la1) * math.cos(d) + math.cos(la1) * math.sin(d) * math.cos(b))
    lo2 = lo1 + math.atan2(
        math.sin(b) * math.sin(d) * math.cos(la1), math.cos(d) - math.sin(la1) * math.sin(la2)
    )
    return math.degrees(la2), (math.degrees(lo2) + 180) % 360 - 180


@pytest.mark.parametrize(
    ("lat", "lon", "km"), [(43.6, -79.4, 5.0), (-60.0, 10.0, 40.0), (85.0, 0.0, 100.0), (0.0, 179.9, 30.0)]
)
def test_points_just_inside_a_circle_lie_in_its_boxes(lat, lon, km):
    boxes = _index._circle_boxes(lat, lon, km)
    rng = random.Random(0)
    for bearing in [0, 90, 180, 270, *(rng.uniform(0, 360) for _ in range(400))]:
        p_lat, p_lon = _destination(lat, lon, bearing, km * (1 - 1e-12))
        assert any(s <= p_lat <= n and w <= p_lon <= e for s, w, n, e in boxes), (bearing, p_lat, p_lon)
    rules = {"label": [{"within": {"point": {"lat": lat, "lon": lon}, "km": km}, "fields": {"city": "In"}}]}
    engine = OverrideEngine.from_documents([(Layer.LOCAL, rules, "local:l.toml")])
    point = _destination(lat, lon, 45, km * 0.999)
    assert engine.apply(Result(*point), *point).city.name == "In"
