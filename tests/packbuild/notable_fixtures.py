"""Small inputs for the notable-place sources: QLever TSV exports per kind and a QRank file.

Invented places in open Pacific water (around 0°N 140°W, as lookup_kit's world).
"""

import gzip

from packbuild.sources.notable import kinds

ENTITY = "<http://www.wikidata.org/entity/{}>"


def literal(text, lang=None):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"' + (f"@{lang}" if lang else "")


def tsv_row(kind, qid, label, lon, lat, sitelinks=5, countries="", aliases="", **codes):
    """One TSV export line for a kind; codes by SPARQL variable (iata0, station_code1 ...)."""
    cells = [
        ENTITY.format(qid),
        literal(label, "en"),
        f"POINT({lon} {lat})",
        str(sitelinks),
        literal(countries) if countries else "",
        literal(aliases) if aliases else "",
    ]
    cells += [literal(codes[v]) if codes.get(v) else "" for v, _ in kinds.code_variables(kind)]
    return "\t".join(cells)


def write_export(path, kind, rows):
    """A TSV export at `path` for kind (a kinds.Kind): rows are tsv_row keyword dicts."""
    header = ["?item", "?label", "?point", "?sitelinks", "?countries", "?aliases"]
    header += [f"?{v}" for v, _ in kinds.code_variables(kind)]
    lines = ["\t".join(header), *(tsv_row(kind, **r) for r in rows)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_qrank(path, views):
    """A QRank file: {qid: views}, most viewed first."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["Entity,QRank", *(f"{q},{v}" for q, v in sorted(views.items(), key=lambda kv: -kv[1]))]
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")
    return path


# kind -> rows; Q1/Q2 are one station listed twice (station building + station), Q3 is a museum that
# is also a landmark, Q7 a defence aerodrome
ROWS = {
    "airport": [
        dict(qid="Q5", label="Alpha International Airport", lon=-139.5, lat=0.5, sitelinks=30, countries="XA",
             aliases="AAA|XAAA|Alpha Airport", iata0="AAA", icao0="XAAA"),
        dict(qid="Q7", label="Alpha Air Force Station", lon=-139.4, lat=0.4, sitelinks=3, iata0="AFS"),
    ],
    "station": [
        dict(qid="Q1", label="Alpha Central railway station", lon=-139.75, lat=0.25, sitelinks=12,
             countries="XA", aliases="Alpha Central", station_code0="ACL"),
        dict(qid="Q2", label="Alpha Central railway station", lon=-139.7501, lat=0.2501, sitelinks=1,
             countries="XA", aliases="Old Central Building", station_code3="AC"),
    ],
    "museum": [
        dict(qid="Q3", label="Alpha Museum", lon=-139.74, lat=0.26, sitelinks=20, countries="XA",
             aliases="The Alpha Museum|alphamuseum.org"),
    ],
    "landmark": [
        dict(qid="Q3", label="Alpha Museum", lon=-139.74, lat=0.26, sitelinks=20, countries="XA",
             aliases="AM"),
        dict(qid="Q4", label="Alpha Tower", lon=-139.745, lat=0.255, sitelinks=90, countries="XA",
             aliases="the Tower"),
        dict(qid="Q6", label="Border Arch", lon=-139.0, lat=1.0, sitelinks=8, countries="XA|XB"),
    ],
}  # fmt: skip
VIEWS = {"Q1": 50_000, "Q2": 1_500, "Q3": 20_000, "Q4": 2_000_000, "Q5": 400_000, "Q6": 5_000, "Q7": 9_000}


def write_cache(cache_dir, rows=ROWS, views=VIEWS):
    """A download cache as packbuild.fetch leaves it: every kind's export and the QRank file, each
    with a sidecar, so the builder reads them without the network."""
    from packbuild.sources import url

    for kind in kinds.KINDS:
        folder = cache_dir / f"notable-{kind.name.replace('_', '-')}"
        path = write_export(folder / "wikidata", kind, rows.get(kind.name, []))
        sidecar(path, url("wikidata", kinds.download_name(kind)))
    qrank_url = url("qrank", "qrank")
    path = write_qrank(cache_dir / "qrank" / qrank_url.rsplit("/", 1)[-1], views)
    sidecar(path, qrank_url)
    return cache_dir


def sidecar(path, source_url):
    path.with_name(path.name + ".json").write_text(
        f'{{"url": "{source_url}", "sha256": "", "size": {path.stat().st_size}, "retrieved": "2026-11-17"}}\n'
    )
