"""Overrides benchmark (not collected by pytest):

    uv run python tests/overrides/bench_overrides.py [RESULTS] [RULES] [--dump FILE]

Applies RULES synthetic override rules (default 1,200, every rule type and area kind, GeoJSON
polygons included) to RESULTS hand-built answers (default 100,000) at synthetic points around
public places, and prints the time (CPU time) and a digest of every answer; `--dump` writes them,
one per line, for diffing.
"""

import hashlib
import json
import random
import sys
import tempfile
import time
from pathlib import Path

from overrides_kit import CALIFORNIA, CANADA, ONTARIO, PEARSON, USA

from placewise.model import Layer, Nearby, Place, Result
from placewise.overrides import OverrideEngine

# synthetic points spread over two public areas: southern Ontario and the San Francisco Bay Area
AREAS = (((42.8, -81.0), (44.5, -78.5), CANADA, ONTARIO), ((37.0, -123.0), (38.5, -121.5), USA, CALIFORNIA))
N_LOCALITIES = 400


def _point(rng, area=None):
    (s, w), (n, e), *_ = area or rng.choice(AREAS)
    return round(rng.uniform(s, n), 5), round(rng.uniform(w, e), 5)


def _locality(k):
    return Place(f"test:locality/{k}", f"Locality {k}", "locality")


def _admin2(k):
    return Place(f"test:admin2/{k}", f"District {k}", "admin2", codes={"cd": str(k)})


def _square(lat, lon, d):
    ring = [
        [lon - d, lat - d],
        [lon + d, lat - d],
        [lon + d, lat + d],
        [lon - d, lat + d],
        [lon - d, lat - d],
    ]
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def rules(n, folder, seed=0):
    rng = random.Random(seed)
    for i in range(10):
        lat, lon = _point(rng)
        doc = {"type": "FeatureCollection", "features": [_square(lat, lon, rng.uniform(0.02, 0.2))]}
        (folder / f"area{i}.geojson").write_text(json.dumps(doc))
    doc = {t: [] for t in ("label", "city", "add", "rename", "hide", "region", "tune")}
    for i in range(n):
        lat, lon = _point(rng)
        kind = rng.random()
        if kind < 0.30:
            area = {"point": {"lat": lat, "lon": lon}, "km": rng.uniform(0.5, 30)}
        elif kind < 0.45:
            d = rng.uniform(0.01, 0.3)
            area = {"bbox": {"south": lat - d, "west": lon - d, "north": lat + d, "east": lon + d}}
        elif kind < 0.50:
            area = {"geojson": f"area{rng.randrange(10)}.geojson"}
        elif kind < 0.55:
            area = {"country": rng.choice(("CA", "US"))}
        elif kind < 0.60:
            area = {"place": _locality(rng.randrange(N_LOCALITIES)).id}
        else:
            area = None
        what = rng.random()
        if area is not None and what < 0.6:
            field = rng.choice(("city", "sublocality", "region", "admin2", "label"))
            doc["label"].append({"within": area, "fields": {field: f"Label {i}"}})
        elif area is not None:
            doc["city"].append({"within": area, "city": f"City {i}"})
        elif what < 0.15:
            doc["city"].append({"locality": _locality(rng.randrange(N_LOCALITIES)).id, "city": f"City {i}"})
        elif what < 0.35:
            add = {"kind": rng.choice(("landmark", "region", "airport")), "name": f"Place {i}"}
            add.update(point={"lat": lat, "lon": lon}, radius_m=rng.uniform(100, 20000))
            if rng.random() < 0.5:
                add["id"] = f"test:added/{i}"
            doc["add"].append(add)
        elif what < 0.55:
            target = rng.choice((_locality(rng.randrange(N_LOCALITIES)).id, f"test:added/{rng.randrange(n)}"))
            doc["rename"].append({"id": target, "name": f"Renamed {i}", "aliases": [f"Alias {i}"]})
        elif what < 0.65:
            doc["hide"].append({"id": rng.choice((PEARSON.id, f"test:added/{rng.randrange(n)}"))})
        elif what < 0.85:
            region = {"id": f"test:region/{i % 40}", "label": f"Region {i}"}
            if rng.random() < 0.5:
                region["members"] = {"cd": [str(rng.randrange(60)) for _ in range(5)]}
            elif rng.random() < 0.5:
                region["polygon"] = f"area{rng.randrange(10)}.geojson"
            else:
                region["remove"] = True
            doc["region"].append(region)
        else:
            tune = (
                {"id": _locality(rng.randrange(N_LOCALITIES)).id}
                if rng.random() < 0.5
                else {"kind": "airport"}
            )
            tune.update(rng.choice(({"tier": rng.randrange(1, 4)}, {"near_km": rng.uniform(1, 10)})))
            doc["tune"].append(tune)
    return OverrideEngine.from_documents([(Layer.LOCAL, doc, "local:bench.toml", folder)])


def results(n, seed=1):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        area = rng.choice(AREAS)
        lat, lon = _point(rng, area)
        locality = _locality(rng.randrange(N_LOCALITIES))
        near = (Nearby(PEARSON, "near", rng.uniform(0, 15)),) if rng.random() < 0.3 else ()
        out.append(
            Result(
                lat,
                lon,
                label=locality.name,
                country=area[2],
                admin1=area[3],
                admin2=_admin2(rng.randrange(60)),
                city=locality,
                locality=locality,
                near=near,
                airport=Nearby(PEARSON, "near", rng.uniform(0, 15)) if rng.random() < 0.2 else None,
            )
        )
    return out


def main():
    args = sys.argv[1:]
    dump = None
    if "--dump" in args:
        i = args.index("--dump")
        dump = Path(args[i + 1])
        del args[i : i + 2]
    n_results = int(args[0]) if args else 100_000
    n_rules = int(args[1]) if len(args) > 1 else 1_200
    with tempfile.TemporaryDirectory() as tmp:
        t = time.process_time()
        engine = rules(n_rules, Path(tmp))
        print(f"{len(engine):,} rules loaded              {time.process_time() - t:8.3f} s")
        answers = results(n_results)
        relabel = lambda r: f"{r.city.name if r.city else '?'}, {r.admin1.name if r.admin1 else '?'}"  # noqa: E731
        engine.apply(answers[0], answers[0].lat, answers[0].lon, relabel=relabel)  # loads the GeoJSON
        t = time.process_time()
        out = [engine.apply(r, r.lat, r.lon, relabel=relabel) for r in answers]
        dt = time.process_time() - t
    print(f"apply x {n_results:,}                {dt:8.3f} s  = {n_results / dt:,.0f} results/s")
    changed = sum(a != b for a, b in zip(answers, out, strict=True))
    print(f"answers changed by a rule: {changed:,}")
    lines = [repr(r.to_dict()) for r in out]
    print(f"answers digest {hashlib.sha256(chr(10).join(lines).encode()).hexdigest()[:16]}")
    if dump is not None:
        dump.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
