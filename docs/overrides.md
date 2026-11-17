# Overrides

Overrides are rules that beat the data. They come in layers, and a higher layer always wins:

| Layer   | Where it lives                                         | Who writes it                    |
|---------|--------------------------------------------------------|----------------------------------|
| `data`  | the packs                                              | the pack build                   |
| `repo`  | `src/placewise/overrides/repo/*.toml`, shipped         | placewise contributors           |
| `app`   | passed in by the calling program (`app_rules=`)        | the app using placewise          |
| `local` | `overrides.toml` in the data directory (or any path)   | you; beats everything            |

Within one layer, rules apply in file order (repo files in name order), so a later rule wins over
an earlier one. Every field a rule changes is cited in the answer:

```python
result.sources["city"]   # "override:local:overrides.toml#2"  (layer:file#rule-number)
```

Rule numbers count through the whole file across all tables, starting at 1. Local files are cited
by name only, so answers never carry your directory layout.

```python
from placewise.overrides import load_overrides

overrides = load_overrides()                       # repo + your local file
overrides = load_overrides(local_path="mine.toml", app_rules={"hide": [{"id": "osm:way/1"}]})
result = overrides.apply(result, lat, lon)
overrides.resolve_name("GTA")                      # ["placewise:region/gta"]
overrides.explain()                                # every rule, its layer and origin
overrides.tuning(place)                            # merged tune knobs for a place
```

The default local file is `<data dir>/overrides.toml` (`placewise data where` prints the data directory).
If it doesn't exist, `overrides.json` beside it is read instead; if neither exists there is no
local layer. A local path you name explicitly must exist.

## File format

A file is a set of TOML arrays of tables, one table per rule: `[[rename]]`, `[[label]]`,
`[[city]]`, `[[region]]`, `[[alias]]`, `[[hide]]`, `[[add]]`, `[[tune]]`. Unknown rule types,
unknown fields and bad values are errors that name the file and the rule number.

TOML needs Python 3.11+ or `pip install tomli`. Without either, write the same structure as JSON
(`overrides.json`): `{"rename": [{"id": "...", "name": "..."}]}`.

### Areas

Several rules take an area (`within`). An area is exactly one of:

```toml
within = { point = { lat = 43.5503, lon = -79.5868 }, km = 1.0 }        # circle
within = { bbox = { south = 37.2, west = -122.6, north = 38.3, east = -121.6 } }
within = { geojson = "east_bay.geojson" }   # polygon file, relative to this overrides file
within = { place = "wikidata:Q50816" }      # the answer mentions this place (admin chain, regions, within)
within = { country = "CA" }                 # ISO 3166-1 alpha-2
```

## Rule reference

### `rename`: call a place something else

Matches the place id wherever it appears in an answer (admin chain, regions, within, near,
airport, water). The old name becomes an alias, so search still finds it.

```toml
[[rename]]
id = "wikidata:Q50816"
name = "Mississauga, ON"
aliases = ["Sauga"]
```

### `label`: set answer fields inside an area

`fields` may set `label`, `city`, `locality`, `sublocality`, `borough`, `region`, `admin1`,
`admin2`. A field that already holds a place is renamed in place (its id stays); an empty field
gets a new place with an `override:` id. `region` puts a region first in `regions`. `label` sets
the label text outright.

```toml
[[label]]
within = { point = { lat = 43.5503, lon = -79.5868 }, km = 1.0 }
fields = { sublocality = "Port Credit" }
```

### `city`: show a different display city

For one locality id, or for every point in an area. Unlike `label`, the city becomes a different
entity (a new `override:` id), since "Bay Area" is not the City of Oakland.

```toml
[[city]]
locality = "wikidata:Q17042"     # Oakland
city = "Bay Area"

[[city]]
within = { bbox = { south = 37.2, west = -122.6, north = 38.3, east = -121.6 } }
city = "Bay Area"
```

### `region`: define a region's membership

Members are codes on the answer's admin places (`{code_name = [values]}`, or `id = [place ids]`),
and/or a GeoJSON polygon. The rule decides membership: points that are members get the region
(added at the end of `regions`, or relabelled in place if the data already has it), and points
that aren't lose it. `remove = true` drops the region from every answer and from search.

```toml
[[region]]
id = "placewise:region/gta"
label = "Greater Toronto Area"
aliases = ["GTA"]
members = { ca_cd = ["3518", "3519", "3520", "3521", "3524"] }   # census divisions

[[region]]
id = "wikidata:Q213205"
remove = true
```

### `alias`: another name for forward search

Only affects name search (`resolve_name`), never reverse lookups. `country` and `near` restrict
where the alias applies (`near` covers searches within 50 km of its point).

```toml
[[alias]]
text = "GTA"
means = "placewise:region/gta"
country = "CA"
```

### `hide`: drop a place from answers

Removes the id from `regions`, `within` and `near`, and clears `airport` / `water` if it is that
place. Hidden ids are also left out of `resolve_name`.

```toml
[[hide]]
id = "osm:way/123456"
```

### `add`: a place the data doesn't have

Matches points within `radius_m` of `point` (default 100 m), or inside `within` when given (the
point is then just where the place is). A matching place goes first in `within`; `airport` kinds
fill the `airport` slot, `water` the `water` slot and `region` goes first in `regions`. Without an
`id`, the place's id cites the rule (`override:local:overrides.toml#4`). An `add` in a higher
layer brings back a place a lower layer hid.

```toml
[[add]]
kind = "landmark"
name = "Celebration Square"
point = { lat = 43.5890, lon = -79.6430 }
radius_m = 300

[[add]]
kind = "park"
name = "Toronto Island Park"
point = { lat = 43.6205, lon = -79.3780 }
within = { bbox = { south = 43.60, west = -79.40, north = 43.635, east = -79.34 } }
```

### `tune`: numeric knobs

Targets one `id` or a whole `kind`, and sets any of `tier`, `near_km`, `fame`, `boost`. Knobs
merge across rules (higher layer, then later rule, wins per knob) and apply once: `tier` is set on
the matching places, and `near` entries farther than their `near_km` are dropped (the lookup reads
`tuning()` to search wider). `fame` and `boost` are ranking inputs read through `tuning()`.

```toml
[[tune]]
kind = "park"
near_km = 5

[[tune]]
id = "osm:way/rattray-marsh"
near_km = 10
boost = 1.5
```

## Repo files and their JSON twins

Each shipped `repo/*.toml` has a `.json` twin so Python 3.10 without tomli reads the same rules
(cited as the `.toml` either way). After editing a repo TOML file, regenerate the twins:

```
uv run python -c "import json, tomllib, pathlib; [p.with_suffix('.json').write_text(json.dumps(tomllib.loads(p.read_text()), indent=2) + '\n') for p in pathlib.Path('src/placewise/overrides/repo').glob('*.toml')]"
```

A test fails if a twin is missing or out of date.
