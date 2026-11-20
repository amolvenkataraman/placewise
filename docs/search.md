# Forward search

Name in, place out, offline: `placewise.find("Yosemite")` returns ranked `Entity` objects
(`placewise.model.Entity`): the place (id, name, kind, codes, aliases, tier), a point guaranteed to
be inside it, its bounding box, a radius (the farthest outline vertex from the point), its outline
on request (`geometry=True`, with `.contains(lat, lon)`), where it is (`city`, `region`, `country`
as ISO alpha-2) and how sure that is (`context_matches`, `context_certain`; see
[How sure the context is](#how-sure-the-context-is)), a score, and `alternates`: the same place as
other packs hold it.
Code: `placewise.search`; constants: `placewise.constants.search`; index: the packs' `names/`
directory (`docs/pack-format.md`).

```python
import placewise

placewise.find("Lake Tahoe")[0].bbox              # BBox(south, west, north, east)
placewise.find("Paris, TX")[0].region             # "Texas"
placewise.find("Paris", country="USA")[0]         # Paris, Texas (the most prominent US Paris)
placewise.find("Springfield", state="IL")         # context as arguments
placewise.find("Victoria", near=(48.43, -123.37)) # Victoria, British Columbia
placewise.find("Lake", within="region:sf-bay-area", kinds="water")
placewise.find("YYZ")                             # Toronto (the city it serves), then the airport
placewise.find("YYZ", kinds="airport")            # Toronto Pearson International Airport
placewise.get("census:0646870", geometry=True)    # by id, with the outline
placewise.outline("iso:US-CA", simplify_m=500)    # the outline as a GeoJSON geometry (lon, lat)
placewise.get("iso:US-CA", geometry=True).geojson(simplify_m=500)  # the whole GeoJSON Feature
placewise.suggest("Mississ")                      # type-ahead: Mississauga ...

geo = placewise.Geocoder(packs=[...])             # Geocoder.find / Geocoder.get: the same objects
```

## Outlines as GeoJSON

`placewise.outline(id, simplify_m=None)` (also `Geocoder.outline`, `Client.outline`) gives a
place's outline as a GeoJSON geometry dict (RFC 7946): positions in (lon, lat) order, a `Polygon`,
or a `MultiPolygon` when the outline has several parts, every hole under the ring that holds it
(an island in a lake in an island is a polygon again), outer rings counter-clockwise and holes
clockwise; None for a place known only as a point. Packs hold outlines as even-odd rings
(`Outline.rings`, (lat, lon)); the export works out which ring is a hole of which.
`simplify_m` drops vertices while every ring stays within that many metres of the original
(Douglas-Peucker, per ring): Natural Earth's California goes from 1,848 vertices to 746 at 500 m,
Canada from 67,781 to 33,094 (its Arctic coast is mostly detail finer than that). Rings smaller than the tolerance (small islands, small holes) are left out, but never all
of them.

`Entity.geojson(simplify_m=None)` makes a `Feature` (id: the place id; `bbox`; properties: name,
kind, tier, codes, city, region, country), with the outline when the Entity has one (`geometry=True`)
and its point otherwise; `Outline.to_geojson()` the bare geometry. `placewise.io.to_geojson(items)`
and `write_geojson(items, path)` make a `FeatureCollection` of Entities, Outlines or Features, for
a "states, counties and parks visited" map:

```python
from placewise.io import write_geojson

visited = [placewise.get(i, geometry=True) for i in ("iso:US-CA", "census:06085")]
write_geojson(visited, "visited.geojson", simplify_m=200)
```

## What a query can be

| Query | Read as |
|---|---|
| `Toronto`, `Lake Ontario`, `Bay Area` | a name: official names, aliases, former names and abbreviations in the packs' name indexes |
| `Springfield, IL`, `Paris, France`, `London, ON, Canada` | name, then context: every part after a comma is read as a country or state (`placewise.text`'s readings); parts that agree narrow each other |
| `Union Station, Toronto` | name, then a place: the place's point becomes a `near` boost |
| `Paris TX` | as `Paris, TX`, when the whole text matches nothing prominent exactly |
| `Bangalore`, `Gurgaon`, `Bombay` | also the city location search knows by that alias (Bengaluru in Karnataka ...) |
| `GTA`, `Delhi NCR` | also the curated region location search knows by that name (`region:gta`) |
| `Peel Region`, `City of Toronto` | also without the generic words, when nothing matched exactly |
| `Mississippi River`, `River Thames` | also the water named without the word |
| `Torono`, `Missisauga` | typo-tolerant matches, when nothing prominent matched exactly |
| `PEI` | an abbreviation of a country, state or county: also that place under its own name in every pack (Prince Edward Island as the Canada pack ranks it) |
| `O'Hare`, `Kempegowda` | also an airport called so with "International Airport" or "Airport" after it, unless the text names a place ("Denver" is the city) |
| `YYZ`, `CYYZ`, `M5V`, `94105`, `560001`, `CA-ON`, `US`, `IND`, `Q1049470` | codes (exact only): IATA, ICAO, postal codes, ISO 3166, Wikidata ids |
| `census:0646870`, `wikidata:Q1049470`, `iso:IN-KA` | placewise ids |
| `43.6426, -79.3871`, map URLs, DMS | coordinates (`geo.parse`): one Entity for the point, named by a reverse lookup, id `geo:lat,lon` |

**Codes mean what people mean.** An airport code without `kinds` means the city the airport
serves: `YYZ` is Toronto, then the airport. The served city is the airports layer's `served`
column when the pack has it, else the GeoNames city within 60 km in the airport's country with the
highest population / (km + 2) (never OurAirports' `municipality`, the airport's own town). A
three-letter code that is also a country's alpha-3 means the airport's city ("BLR": Bengaluru, not
Belarus) unless the country is commonly written that way ("IND", "CAN", "USA" ...). `kinds="airport"` or the word
"airport" in the text ("YYZ airport") puts the airport first. Postal codes mean the postal area.

## Context arguments

All optional and combinable; context in the text and arguments combine, and the arguments win
where they disagree (`find("Paris, TX", country="FR")` ignores TX).

| Argument | Accepts | Effect |
|---|---|---|
| `country=` | alpha-2, alpha-3, numeric, name or alias ("US", "USA", "United States", "U.S."), or a list | only places in it |
| `admin1=` / `state=` | "TX", "Texas", "US-TX", "Ontario", "KA", or a list | only places in it |
| `near=(lat, lon)` | a pair or a `Point` | boost by distance from the place's extent; with `radius_km=`, only places within it |
| `bbox=(south, west, north, east)` | a tuple or `BBox` | only places whose point is inside |
| `within=` | a place id or name ("GTA", "region:sf-bay-area", "census:06085") or an Entity | only places whose point is inside its outline |
| `kinds=` | PlaceKind values or everyday words: city, park, water, lake, airport, postal_code, state, county, metro ... | only those kinds |
| `strict=False` | | every filter above becomes a boost (x0.2 per failed filter) |
| `prefix=True` | | names that start with the text (what `suggest` does) |
| `worldview=` | as `lookup` | the country reported for places in disputed areas (`docs/worldviews.md`) |

Country and state filters use the de facto boundaries of the world pack's countries and admin1
layers at each place's point.

## How sure the context is

An Entity's `city`, `region` and `country` follow reverse lookup's rules at its point: the
containing polygon, or, just off a coast, the nearest country and region within the territorial sea
(12 nmi), as `lookup` has them; a place that needs a city (a neighbourhood, postal code, airport or
landmark) or another worldview gets a full reverse lookup, where country packs correct the region
(US counties' states, Indian states). The answer is the best placewise has, but not always right:
Natural Earth's 1:10m outlines are generalised, so the Statue of Liberty, on an island off New
Jersey's shore, falls in New Jersey's admin1 polygon. Each Entity says how sure it is:

- `context_matches`: for each of `city`, `region` and `country` that is set, a `Match` as
  `Result.matches` has it: `within` (the polygon holds the point), `offshore` (taken from the
  territorial sea) or `near` (a fallback: the nearest region polygon in a sliver between the
  layers, the nearest town for `city`), with `distance_km`.
- `context_certain`: False when the country or region isn't guaranteed: either was found other than
  `within`, or the point is within 5 km (`constants.search.CONTEXT_BORDER_KM`) of another country's
  outline, or of another region's where the world pack's admin1 decided the region (a country
  pack's region has fine borders of its own). A coast with nothing across it doesn't count. True
  when there is no context (far at sea). The city doesn't enter it: towns are often nearest
  fallbacks, and `context_matches["city"]` says so.

Why 5 km, measured (2026.11 packs, random points in the US, Canada and India, the world pack's
admin1 against the country packs' states and provinces): 69 of 34,883 US points, 58 of 30,299
Canadian and 291 of 21,311 Indian points fall in the wrong 1:10m admin1 polygon. 5 km from another
outline catches 99% of the US misses, 90% of the Canadian and 91% of the Indian ones (the median
miss is 0.3, 0.8 and 1.1 km inside), while flagging 5%, 2% and 9% of all points; 10 km would catch
100%, 98% and 94%, flagging more. 5 km is also the usual 0.5 mm drawing tolerance at
the 1:10,000,000 scale the data is generalised for.

The card shows why after the context: `Point Roberts  (Washington, US · near a border)`, or
`· offshore`, or `· outside its outline`; JSON and `Client.find` carry both fields
(`"context_certain": false`). `Result.certain` is the lookup's counterpart without the border
distance: True when its country and admin1 hold the point.

## Ranking

`score = match ** 3 x name kind x (0.15 + 0.85 x rank) x context x near x factor x namesake`

- **match**: 1 for exact names and codes; prefix matches `0.6 + 0.4 x len(query) / len(name)` (not
  cubed: while typing, the prior decides); typo matches
  `1 - edits / length`, then x0.85, and x0.85 again for a typo of an alias, former name or
  abbreviation (big places have many alternate spellings: "Colaba" is the Mumbai neighbourhood,
  not Cuiabá, once spelled Culaba). Aliases are worth x0.97, former names and abbreviations x0.95.
- **rank**: the index's prior prominence, 0..1 and comparable across packs (population, area, park
  tier, fame): countries 0.85-1, US, Canadian and Indian states 0.75-0.85, other admin-1 units
  0.5-0.8 by the people of their cities (Portland, Jamaica's parish, comes after Portland, Oregon),
  counties and census divisions 0.45-0.7 by population (Clark County is Nevada's), a 3M city
  ~0.85, a hamlet ~0.3, a Canadian community shown at 1:1.2M (Scarborough) ~0.5.
- **context**: the text's context: 1 in its likeliest reading, 0.9 in a later one ("CA" as Canada),
  0 outside, or 0.2 for everything when nothing is inside.
- **near**: `0.25 + 0.75 x exp(-km / scale)`, km from the near point to the place's extent; a
  place's reach grows with its rank: `scale = 250 x min(1, rank / 0.8) ** 2` km (at least 5): a
  neighbourhood ~16 km, a town ~60 km, a 500k city ~165 km, a big city or a state 250 km, so
  typing "Kora" near Bengaluru gives Koramangala before Koratagere, a town 70 km away.
- **factor**: city aliases from location search x0.98; places an override rule names x2; waters
  found without the word "river" ("Mississippi River" is Natural Earth's "Mississippi") x0.97;
  airports found with "(International) Airport" added x0.97; a place found under its own name
  for an abbreviation ("PEI") the abbreviation's x0.95.
- **namesake**: x0.7 for what is named after a place the query also names, when that place
  (a city, county, state, region, neighbourhood or country) has a rank of 0.3 or more: a station,
  airport, university, building or landmark of that name (Richmond the station, Miami University
  as "Miami"), anything else known by it as an alias (Boise National Forest as "Boise"), a code
  that reads as the name when typed as a word ("Goa", Genoa's IATA code) or, unless it is an airport
  code, that a place has as an abbreviation ("SF": San Francisco, not a station's code), and, while typing, anything not a place whose name is the place's name and
  more words (San Francisco Zoo for "San Fran"). A city found only by its airport's code doesn't
  count ("YYZ" still gives Toronto, then the airport). While typing, facilities also score x0.85
  (Toronto before Toron, a castle, for "Toro"), and a code that is a postal code comes before
  other codes ("10001": the ZIP Code, not a railway station's code).

Typo matches are only gathered when no exact match has a prior of at least 0.35, so a typo of a big
city ("Torono") still finds it while exact names of real places win; and when the text matches
anything exactly, only typos of one letter compete ("Malabar Hill", the Mumbai neighbourhood, not
Barabar Caves, known as Barabar Hill).

## One place, several packs

Toronto is a GeoNames city (world), a census subdivision, a census division and a metro area
(can); Yosemite is an outline (usa-parks) and a point (world-parks). Candidates that share a name,
whose kinds can describe one place (every settlement kind: locality, borough, sublocality, county,
region; otherwise the same kind) and that overlap (one's point inside the other's outline, or two
points within 15 km) become one Entity: the best-shaped one (a locality over a county over a metro
area; an outline over a point; a country pack's outline over the world pack's) with the others in
`alternates`. Rows of one feature stored in parts (`pad-us:x`, `pad-us:x#2`) always merge. A state
and a city of the same name (New York) stay apart.

## Overrides

Alias rules (`overrides/repo/aliases.toml`, app and local files) make a name mean an id; rename
rules rename it in results (the old name joins its aliases) and make the new name findable; hide
rules (and removed regions) take a place out of results and `get`; add rules with an id are found
by name and by `get`. See `docs/overrides.md`.

## Surfaces

- CLI: `placewise find "Lake Tahoe" [--limit --country --state --near LAT,LON --radius-km --bbox S,W,N,E
  --within --kind --loose --prefix --worldview --json --geometry --packs DIR]`, printing each
  Entity's card (`str(entity)`: name and context, kind, point, extent, id, score, alternates).
- Server and local service: `GET /v1/find?q=...` with the same arguments (`near=lat,lon`,
  `bbox=s,w,n,e`, lists comma-separated, `prefix=1`, `strict=0`, `geometry=1`), `POST /v1/find` with
  them as JSON (keeps `near` out of URLs), `GET /v1/get?id=...`; `placewise.Client.find/get`.
- Location search: `placewise.search.SearchGazetteer` is a `Gazetteer` for
  `placewise.text.parse_location`, confirming cities (exact name or alias, settlement kinds only) and
  returning their Place with point, box, id, `codes["iso2"]` and `codes["admin1"]`.

## Speed

Each pack's name index is memory-mapped, its fuzzy trigram postings included; the first query
opens what it touches. Measured in fresh processes on world + usa + can + ind + world-water + the
three park packs (`tests/search/bench_search_coldstart.py`): the first query for a name ~0.1-0.25 s,
the first typo ~0.3 s, the first airport or postal code ~0.4 s (its results carry a city, so the
reverse lookup's indexes load), then a median of ~1.5 ms per query and under 10 ms for every query
in the e2e list (typos ~6 ms). Packs written before the postings were stored build them in memory
on the first typo (~0.7 s more). Entities' context (city, region, country) is looked up for all
results at once, with only the steps that place a point (no water, airport or time zone polygons),
and cached (4,096 points per worldview). Coordinates typed as text get a full reverse lookup, whose
first call builds the water shore index (~6 s). Outlines are built only with `geometry=True`: a
country's outline has tens of thousands of vertices.

## Limits

- Results are what the open packs name: notable places (CN Tower, universities, stations) need the
  `world-notable` pack; India's cities come from GeoNames points until India city outlines exist.
- The `country=`/`state=` filters read de facto boundaries; under another worldview, a place in a
  disputed area is filtered by where it is administered, and only its reported `country` follows the
  worldview.
- English names only.
- Prominence comes from population, area, tiers and page views, not from what people search for:
  Manali (Chennai's suburb) outnumbers Manali (the Himachal Pradesh hill town), and India Post's
  neighbourhoods rank like hamlets.

## Ranking evaluation

`tests/e2e/test_e2e_search_quality.py` runs 364 queries (`search_quality_cases.json`: big and small
cities, ambiguous names, states, districts, counties, neighbourhoods, parks, waters, landmarks,
airport and postal codes, typos, prefixes, former names and transliterations, mostly in the US,
Canada and India) and prints top-1 and top-3 accuracy per category and warm latency. On the
2026.11 packs: top-1 99.7%, top-3 100% (before this evaluation's ranking work: 86.7% and 96.3%;
98.3% and 99.4% on the first 354 before the fixes for abbreviations, airports by name, typos
against exact names and nearby small places); warm median 2.1 ms, p95 8 ms.
