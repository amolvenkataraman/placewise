# packbuild

Turns public datasets into pack layers (see `docs/pack-format.md`). Build-time only: it is not in
the wheel. Tests live in `tests/packbuild/` and never touch the network.

```
uv run python -m packbuild.world --version 2026.11     # writes .cache/packbuild/out/world-2026.11/
```

Downloads are cached once in `.cache/packbuild/` (gitignored) with a `<file>.json` sidecar holding
the URL, SHA-256, size and retrieval date; `--refresh` downloads again. Nothing downloaded is
committed.

## World pack

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `countries` | polygon | Natural Earth 1:10m admin-0 countries | public domain |
| `admin1` | polygon | Natural Earth 1:10m admin-1 states/provinces | public domain |
| `cities` | point | GeoNames cities1000 + admin1CodesASCII + countryInfo | CC BY 4.0 |
| `airports` | point | OurAirports airports.csv (large, medium, scheduled small) | public domain |

Attribution records (`placewise.model.Source`) are in `packbuild/sources/__init__.py`; building
them checks each licence against `placewise.constants.licences`.

Ids: `iso:CA`, `iso:CA-ON` where the ISO code is real and unique, otherwise Natural Earth's own
code (`ne:SOL`, `ne:BIH-4801`); `geonames:<id>`; `ourairports:<ident>`.

Natural Earth's default files draw borders de facto. Its per-worldview attributes (`ADM0_A3_XX`,
`FCLASS_XX`) are kept as str columns so a worldview choice can be offered later.

## Time zones

The world pack carries no time-zone polygons. The usual source, timezone-boundary-builder, is
built from OpenStreetMap and is ODbL (share-alike), and share-alike data may only go in the
separate share-alike pack (`placewise.constants.licences.SHARE_ALIKE`), never in `world`.

Plan:

- **Now:** every GeoNames city carries its IANA zone (`cities.timezone`). A point's zone is the
  zone of the nearest city *in the same country* (country from the `countries` polygon), so a
  point near a border doesn't borrow the neighbour's zone. Good enough for almost all populated
  places; wrong in sparse areas cut by a zone line (e.g. parts of the US Midwest, Russia, Brazil).
- **Later:** zone polygons arrive with the OSM-based share-alike pack, with the ODbL
  derived-database offer that licence requires. When it is installed, polygons win; the
  nearest-city rule stays as the fallback.
