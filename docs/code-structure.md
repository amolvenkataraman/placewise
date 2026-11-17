# Code structure

Every folder has one bounded purpose; code goes where its purpose is, never where it is convenient.
If a module doesn't fit any folder's purpose below, the map is wrong: change this page first.

## The map

| Package | Purpose | Never contains |
|---|---|---|
| `geo/` | Pure maths on coordinates: distances, bearings, shapes, projections, encodings, sun | data files, I/O, packs |
| `tracks/` | The `Track` model and everything computed from tracks | file parsing (that's `io/`) |
| `io/` | File formats in and out: `io/tracks/` (GPX, FIT, TCX ...), `io/polygons/` (GeoJSON, shapefile) | analysis |
| `privacy/` | Location-privacy transforms and the privacy audit | file formats |
| `model/` | Shared dataclasses: results, places, geometry, settings, rules | behaviour beyond validation and dict round trips |
| `constants/` | Fixed values: standards and physical constants, file-format codes, thresholds and defaults, and all country and region reference tables (`constants/countries/`) | functions with logic |
| `packs/` | The pack file format: write and read | downloading |
| `store/` | Downloading, verifying and installing packs | reading pack contents |
| `geocode/` | Answering place questions from packs: `geocode/reverse/` (point to place), `geocode/text/` (parsing location strings); forward search joins later | file formats, HTTP |
| `overrides/` | Repo, app and local override rules and their engine | settings loading |
| `config/` | Loading settings: `placewise.toml`, environment, TOML/JSON parsing | override rules |
| `attribution/` | The source registry (`attribution/sources/*.json`, one file per purpose listing sources per region) and attribution output | build code |
| `service/` | Network access: `service/server/` (HTTP API), `service/local.py` (cached local service), `service/client.py` | lookup logic |
| `cli/` | The `placewise` command, one module per command group | logic the library lacks |

Outside the package: `packbuild/` turns public datasets into packs (`packbuild/sources/<region>/`
loaders, `packbuild/packs/` one builder per pack, release tooling); `tests/` mirrors `src/` exactly;
`docs/` holds specs and guides.

## Rules

- **Size:** a module stays around 300 lines, 400 at most; split by responsibility, not arbitrarily.
  A package holds about 8 modules; past that, group by subject into subpackages.
- **Public API:** users import from packages (`from placewise.io import read_gpx`,
  `placewise.geo.distance`), which re-export; modules starting with `_` are private and may move.
- **Dependencies point one way:** `constants` and `model` import nothing above them; `geo` uses
  only those; `geocode` may use `packs`, `store`, `config`, `overrides`; nothing imports `cli` or
  `service`.
- **Tests mirror src:** `src/placewise/io/tracks/gpx/reader.py` is tested in
  `tests/io/tracks/test_gpx_reader.py`. Test file names stay unique across the suite (pytest's
  default import mode needs it); shared fixtures live in a `*_kit.py` beside the tests that use them.
- **Country naming:** anything named after a country (folders, files, registry region keys, pack
  names) uses the lower-case ISO 3166-1 alpha-3 code: `constants/countries/usa/`,
  `datasets/regions/can.json`, `ind`. Alpha-3 codes are never Python keywords (alpha-2 `in` is).
  Data values keep the standard alpha-2 (`iso2`, ids like `iso:IN-KA`).
- **No app names:** placewise is general-purpose; features are described by what they do
  ("location search"), never by an app that uses them.
- **Data lives with its purpose:** reference tables in `constants/countries/`, the source registry
  in `attribution/sources/`, override rules in `overrides/repo/`, curated datasets we maintain
  ourselves (regions, naming rules, aliases) in `datasets/` at the repo root, with any copy the
  package needs offline generated from them; never inside logic packages.
