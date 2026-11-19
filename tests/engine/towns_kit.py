"""A synthetic world-towns pack over lookup_kit's invented world (open Pacific water).

Alpha City   centre  0.60..0.90 N, 139.60..139.42 W  holds Alpha City (1M) and Alpha Docks
Tinyville    town    0.73..0.77 N, 139.39..139.31 W  holds Tinyville (1k), 17 km east of Alpha City
Zed Harbour  centre  in Betaland's Zed Peninsula, but drawn as Alphaland's (XA): never used
Gamma Port   centre  on Gammaland (XC), which Alphaland's worldview gives to XA
Lost Town    town    named after a place the world pack doesn't have: never used
"""

from lookup_kit import CREATED, box_feature

from placewise.packs import LayerData, write_pack

TOWNS = [
    # box, id, name, geonames, class, country, population
    ((0.60, -139.60, 0.90, -139.42), "ghs:XA:1", "Alpha City", "geonames:1", "centre", "XA", 1_200_000),
    ((0.73, -139.39, 0.77, -139.31), "ghs:XA:2", "Tinyville", "geonames:2", "town", "XA", -1),
    ((0.45, -138.10, 0.55, -138.00), "ghs:XA:6", "Zed Harbour", "geonames:6", "centre", "XA", -1),
    ((2.20, -139.80, 2.30, -139.70), "ghs:XC:5", "Gamma Port", "geonames:5", "centre", "XC", 60_000),
    ((0.10, -139.95, 0.15, -139.90), "ghs:XA:99", "Lost Town", "geonames:99", "town", "XA", -1),
]


def towns_layer(rows=TOWNS):
    columns = {
        name: [r[1 + i] for r in rows]
        for i, name in enumerate(("id", "name", "geonames", "class", "country", "population"))
    }
    return LayerData(
        "towns", "polygon", columns, ("ghsl", "geonames"), features=[box_feature(*r[0], r[1]) for r in rows],
        types={"population": "i4"}, nulls={"population": -1},
    )  # fmt: skip


def write_towns(out_dir, rows=TOWNS):
    about = {"kind": "towns", "covers": ["*"], "requires": ["world"]}
    return write_pack(out_dir, "world-towns", "2026.11", [towns_layer(rows)], created=CREATED, about=about)
