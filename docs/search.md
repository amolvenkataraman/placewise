# Forward search

Name in, place out, offline: `placewise.find("Yosemite")` returns ranked `Entity` objects
(`placewise.model.Entity`): the place (id, name, kind, codes, aliases, tier), a point guaranteed to
be inside it, its bounding box, a radius (the farthest outline vertex from the point), its outline
on request (`geometry=True`, with `.contains(lat, lon)`), where it is (`city`, `region`, `country`
as ISO alpha-2), a score, and `alternates`: the same place as other packs hold it.
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
placewise.suggest("Mississ")                      # type-ahead: Mississauga ...

geo = placewise.Geocoder(packs=[...])             # Geocoder.find / Geocoder.get: the same objects
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
| `Torono`, `Missisauga` | typo-tolerant matches, when nothing prominent matched exactly |
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

## Ranking

`score = match ** 3 x name kind x (0.15 + 0.85 x rank) x context x near x factor`

- **match**: 1 for exact names and codes; prefix matches `0.6 + 0.4 x len(query) / len(name)` (not
  cubed: while typing, the prior decides); typo matches
  `1 - edits / length`, then x0.85. Aliases are worth x0.97, former names and abbreviations x0.95.
- **rank**: the index's prior prominence, 0..1 and comparable across packs (population, area, park
  tier, fame): countries 0.85-1, states 0.7-0.85, a 3M city ~0.85, a hamlet ~0.3.
- **context**: the text's context: 1 in its likeliest reading, 0.9 in a later one ("CA" as Canada),
  0 outside, or 0.2 for everything when nothing is inside.
- **near**: `0.25 + 0.75 x exp(-km / 250)`, km from the near point to the place's extent.
- **factor**: city aliases from location search x0.98; places an override rule names x2.

Typo matches are only gathered when no exact match has a prior of at least 0.35, so a typo of a big
city ("Torono") still finds it while exact names of real places win.

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
