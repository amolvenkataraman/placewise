<!-- header:start -->
<div align="center">

<img alt="placewise: Offline geocoding that names places the way people do, plus a geo toolkit. No API bills." src="https://raw.githubusercontent.com/amolvenkataraman/placewise/master/.github/assets/banner.svg" width="100%">

![python: 3.10+](https://img.shields.io/badge/python-3.10%2B-0f6f68?labelColor=15181c&color=0f6f68)
[![licence: Apache-2.0](https://img.shields.io/badge/licence-Apache--2.0-0f6f68?labelColor=15181c&color=0f6f68)](https://github.com/amolvenkataraman/placewise/blob/master/LICENSE)
[![data: placewise-data](https://img.shields.io/badge/data-placewise--data-0f6f68?labelColor=15181c&color=0f6f68)](https://github.com/amolvenkataraman/placewise-data)

[Why](#why) · [Coverage](#coverage) · [Quick start](#quick-start) · [What it does](#what-it-does) · [Data](#data) · [Status](#status)

</div>

<a href="https://haiscale.amolven.com/M2/"><img alt="HAI Scale M2, Mixed, even split. Placewise's design is mine: the scope, the naming rules, the data and licence choices, the worldview policy and the code structure. AI coding agents wrote much of the code and docs to that design; I steered, reviewed and tested the work. Provided as is and where is, with no warranty." src="https://raw.githubusercontent.com/amolvenkataraman/placewise/master/.github/assets/hai.svg" width="100%"></a>

<sub>Not an official source of place names or boundaries. Full terms: [DISCLAIMER.md](https://github.com/amolvenkataraman/placewise/blob/master/DISCLAIMER.md)</sub>
<!-- header:end -->

**TL;DR:** the free way to turn a GPS point into a place name is "find the nearest big city within
some radius", which is how a photo taken on the Canadian side of Niagara Falls ends up in Buffalo,
New York, and a boat on Lake Ontario ends up in Rochester. The good way is Google's Geocoding API,
which is lovely until you look at the bill: roughly **$5 per 1,000 points**, so naming one 100k-photo
library costs about $500, a location history of a few hundred thousand points about $1,000, and you
pay again every time the data changes, while every place you have ever been goes to Google.
placewise is the third option: the answer a person would give, computed on your own machine, for free.

## Status

> [!WARNING]
> **Early alpha.** It is usable, but expect rough edges and breaking changes.
>
> **Works today:** reverse lookup on the world data (countries, states and provinces, 172k cities,
> airports, time zones by polygon), with full depth for the **US, Canada and India** (municipality,
> county or district, metro area, ZIP / FSA / PIN code, neighbourhoods), first naming rules ("Las
> Vegas" for the Strip, Mississauga for Pearson, Gurugram in Haryana), curated regions (GTA, GTHA,
> Bay Area, Delhi NCR ...), water ("Over Lake Ontario"), US and Canadian parks ("within Yosemite
> National Park"), worldviews (default de facto; `IN` answers India for every area India claims),
> forward search (`placewise.find("Yosemite")`, codes, typos, context such as `country="USA"`;
> `docs/search.md`), location-string parsing, the geo toolkit, track files, privacy tools, a local
> service and a self-hosted web server.
>
> **Doesn't work yet:** notable places and
> universities, India state/district/city outlines (India uses PIN-code areas for now), UK,
> Europe, Australia and most other countries beyond the world baseline, elevation, roads and
> trails, the `reverse`/`explain` CLI commands, Docker. Expect slow first lookups (indexes
> are built on first use) and roughly 25–50k points/s after that.
>
> **Install:** `pip install --pre placewise` (alpha). Only the world pack installs on first use;
> add country packs with `placewise data install usa can ind`, or turn on auto mode
> (`placewise data mode auto`) to fetch them when a lookup first needs them (see [Data](#data);
> `placewise data status` shows them all).

## Coverage

Detailed data is built for the **United States, Canada and India**. Everywhere else is covered by
world-wide datasets, so answers are sensible but coarser. ●●● official boundaries at full detail ·
●● good, approximate in places · ● basic (nearest point or coarse outline) · — not available.

| Layer | United States | Canada | India | Europe & UK | Asia-Pacific | Latin America & Caribbean | Africa & Middle East |
|---|---|---|---|---|---|---|---|
| Country | ●●● | ●●● | ●●● | ●● | ●● | ●● | ●● |
| State / province (admin1) | ●●● Census | ●●● StatCan | ●●● states from PIN + LGD | ●● Natural Earth 1:10m | ●● | ●● | ●● |
| County / district (admin2) | ●●● Census counties | ●●● census divisions | ●● districts (LGD, from PIN areas) | — | — | — | — |
| City / locality | ●●● incorporated places + CDPs, ZIP postal city | ●●● municipalities + named places (CGNDB) | ●● city corporations / ULBs (from PIN areas) | ● nearest GeoNames city | ● | ● | ● |
| Neighbourhood | ●● GeoNames sections | ●● CGNDB neighbourhoods | ●● post-office areas | ● GeoNames sections | ● | ● | ● |
| Metro / region | ●●● metro areas (CBSA/CSA) + curated (Bay Area …) | ●●● CMAs + curated (GTA, GTHA …) | ●● curated (Delhi NCR, MMR, BMR) | — | — | — | — |
| Postal code | ●●● ZIP areas (ZCTA), optional pack `usa-zip` | ●● FSA (first 3 characters) | ●●● PIN-code areas | — | — | — | — |
| Time zone | ●●● by county | ●●● by division | ●●● | ●● by admin1 | ●● | ●● | ●● |
| Parks & protected areas | ●●● NPS, USFS, state (PAD-US); city and county parks: optional pack `usa-parks-local` | ●●● CPCAD (no city parks) | ● Wikidata points ("near" only) | ● Wikidata points | ● | ● | ● |
| Lakes, rivers, seas | ●● Natural Earth + HydroLAKES ≥ 10 km² | ●● | ●● (many lakes unnamed) | ●● | ●● | ●● | ●● |
| Airports | ●●● OurAirports + city served | ●●● | ●●● | ●●● | ●●● | ●●● | ●●● |
| Notable places | ●●● ~38k (Wikidata) | ●● ~4k | ●● ~12k | ●●● | ●● | ●● | ● |
| Search (name → place) | ●●● every layer above | ●●● | ●●● incl. old names (Bangalore, Gurgaon) | ●● cities, admin1, water, parks, landmarks | ●● | ●● | ●● |

Worldviews: the default is de facto (who administers the ground); `worldview="IN"` answers India,
with its state, for every area India claims; `"CN"` puts Taiwan, Hong Kong and Macau in China
(`docs/worldviews.md`).

**Current limitations**

- Outside the US, Canada and India the city is the nearest notable GeoNames place, not a municipal
  boundary, and state lines are Natural Earth's 1:10m outlines (a few hundred metres off at borders).
- India's districts and cities are unions of PIN-code areas: state lines agree with an independent
  reference 99.7% of the time, districts 85%; large fringe PIN areas can fall outside a city, and
  satellite cities (Salt Lake → Bidhannagar) aren't rolled up yet. India has no open park outlines.
- Canada's postal data stops at the FSA (M5V); full six-character postcodes aren't open data.
- Lakes under 10 km² and rivers below Natural Earth's detail are missing; HydroLAKES names are sparse
  outside North America.
- Parks outside the US and Canada are points with a radius, so they're "near", never "within".
- Search ranks well-known places first; very small or ambiguous names may need a `country=` or
  `near=` hint. English names only.
- No street addresses or house numbers (not a goal).

**Planned**

- India: town and village points, satellite-city roll-ups, more metro regions (HMDA, CMDA, PMRDA),
  park outlines if an openly licensed source appears.
- US and Canada: county subdivisions (New England towns), city neighbourhood polygons from open city
  portals, smaller lakes.
- World: municipal outlines from openly licensed global sources (e.g. GHS settlement areas,
  geoBoundaries where the licence allows), better parks, reservoirs.
- Speed: faster boundary queries and first lookups; a readable result card and `placewise lookup` in
  the terminal.

## Why

Most offline geocoders (and many apps built on GeoNames) label a point with the nearest place above
some population inside a radius. It's simple and it's wrong in ways people notice immediately:

| Point | Nearest-city radius answer | placewise | Why the radius gets it wrong |
|---|---|---|---|
| Fort Erie, Ontario | Buffalo, New York (country: Canada) | Fort Erie, Ontario, Canada | City and country come from opposite sides of the border |
| The Las Vegas Strip | Paradise | Las Vegas (in Paradise CDP) | Legally correct, but nobody says Paradise |
| Emeryville, California | Oakland | Emeryville | A small incorporated city next to a big one |
| Toronto Pearson airport | Toronto | at YYZ, Mississauga | No airport awareness; the airport isn't in Toronto |
| Gurugram, Haryana | Delhi, state Delhi | Gurugram, Haryana · Delhi NCR | The nearest place is across a state line |
| A boat on Lake Ontario | Rochester, 50 km away | Over Lake Ontario | Water has no cities, so the radius reaches for one |
| Mid-Atlantic, 50 N 30 W | a town 1,176 km away | Over the North Atlantic Ocean | Same, but worse |
| Yosemite Valley | Yosemite Valley | Yosemite Valley · Yosemite National Park | No park layer |

And the alternatives:

| Option | Cost | Catch |
|---|---|---|
| Google Geocoding API | ~$5 per 1,000 requests after a small free allowance | Every coordinate goes to Google; terms restrict storing and reusing results |
| Mapbox, HERE, OpenCage, LocationIQ | Cheaper than Google, still metered | Coordinates leave your machine; storage terms vary; rate limits for bulk history |
| Self-hosted Nominatim / Photon / Pelias | Free | ~1 TB of disk and 64 GB+ of RAM for the planet, hours to import, ops work; "city" follows OSM tagging |
| reverse_geocoder and similar | Free, tiny | The same nearest-city radius as above |
| **placewise** | Free; code under 1 MB, data packs of tens of MB per region | No street addresses or house numbers (not a goal); English names only for now |

placewise works from real boundaries (municipalities, counties, census areas, postal areas, water
bodies, parks) built from open government and open-data sources, and only falls back to "nearest
city" where nothing better exists. Every answer says which dataset and rule produced it, and you
can override any of it.

It is built for everyone from someone who just wants their Yosemite photos labelled to GIS
professionals: plain words on the simple path, precise terms (EPSG codes, ellipsoids, error
bounds) one step away.

## Quick start

```python
import placewise

r = placewise.lookup(43.6426, -79.3871)       # downloads the world pack on first use
r.label                                       # "Toronto, Ontario, Canada"
r.admin1.codes, r.tz, r.airport               # ISO codes, "America/Toronto", Nearby(YTZ, 1.8 km)
placewise.Geocoder().lookup_many(lats, lons)  # vectorised, tens of thousands of points/s

r = placewise.lookup(36.1147, -115.1728)      # fetches the usa pack first (auto mode): the Las Vegas Strip
r.locality.name, r.sublocality.name           # "Las Vegas", "Paradise" (the census place)
r.postal.name, r.admin2.name                  # "89109", "Clark County"

placewise.lookup(35.9208, 74.3089, worldview="IN").label   # "Gilgit, Ladakh, India" (docs/worldviews.md)

placewise.find("Yosemite")[0]                 # Entity: place, a point inside it, bbox, radius, context
placewise.find("Paris", country="USA")[0]     # Paris, Texas; also state=, near=, within=, kinds=
placewise.find("YYZ")[0].place.name           # "Toronto" (the city it serves); kinds="airport" for the airport
placewise.get("census:0646870")               # by id; placewise.suggest("Mississ") for type-ahead

from placewise.text import parse_location
parse_location("US-CA-Menlo Park; Remote - US and Canada")  # structured places, offline
```

`print(r)` shows a readable card (the label and coordinates, then one aligned line per field with
its source; `r.card()` adds colour on a terminal, Jupyter shows a table); `repr(r)` stays exact.
From the command line: `placewise lookup 43.6426 -79.3871` prints the card (`--json`,
`--worldview IN`, `--packs DIR`), `placewise lookup --csv points.csv --out named.csv` names a
whole file (lat/lon columns; `--lat-column`, `--lon-column`), and `placewise find "Lake Tahoe"`
prints a card per place found (`--json` for Entities).
The same lookups run as a local service or a self-hosted web server (`placewise serve`, see
`docs/self-hosting.md`), with `placewise.Client` offering the identical interface.

## What it does

- **Forward search** (`docs/search.md`): names, aliases, codes (IATA, postal, ISO, Wikidata),
  typos and prefixes to places with a point inside, box, radius, outline and context; context
  from the text ("Paris, TX") or arguments (country, state, near, bbox, within, kinds).
- **Reverse lookup** (`docs/naming.md`): three names per point (sublocality, locality, city),
  county or district, metro and curated regions, postal area, time zone (by polygon), nearest
  airport, water body (`docs/water.md`), parks (`docs/parks.md`), with the source of every field.
- **Worldviews** (`docs/worldviews.md`): de facto by default; per-country views (e.g. `IN`, `CN`)
  and an operator lock for services that must follow one country's map.
- **Overrides** (`docs/overrides.md`): rename, relabel, add or hide places, from the repo, your app
  or a local file.
- **Location search** (`docs/text-parsing.md`): parse messy place strings ("Greater Toronto Area",
  "Remote - EMEA", "Bengaluru (BLR)") into structured places, with filters that explain themselves.
- **Countries and groups** (`docs/world.md`): `placewise.world` for countries, subdivisions, 72
  country groups with dated memberships (EU, Schengen, NATO, EMEA ...) and country profiles.

## Geo toolkit (`placewise.geo`), no data needed

```python
from datetime import date
from placewise import geo

geo.distance(43.6532, -79.3832, 45.5019, -73.5674)                       # km, haversine
geo.distance(43.6532, -79.3832, 45.5019, -73.5674, method="geodesic")    # Karney, WGS84
geo.initial_bearing(43.65, -79.38, 45.50, -73.57)                        # degrees
geo.destination(43.65, -79.38, bearing=45, distance_km=10)
geo.parse("43°38′33.2″N 79°23′13.4″W")                                   # also Google/Apple/OSM URLs
geo.to_utm(43.6426, -79.3871)                                            # also UPS, MGRS, ECEF, ENU
geo.plus_code_encode(43.6426, -79.3871)
geo.sun_times(43.6426, -79.3871, date(2026, 6, 21))
```

Also: geohash, map tiles and quadkeys, encoded polylines, line simplification, nearest point on a
line, spherical areas, antimeridian-aware bounding boxes, a two-stage polygon index for detailed
GeoJSON or shapefile boundaries, and a registry of every coordinate system used with its EPSG code
(`placewise.constants.crs`).

## Tracks (`placewise.tracks`, `placewise.io`)

```python
from placewise.tracks import Track

track = Track.read("ride.fit")        # GPX, FIT, TCX, KML/KMZ, GeoJSON, NMEA or CSV, detected from content
track = track.clean()                 # sort, dedupe, drop invalid fixes, remove spikes, split gaps
track.stats()                         # distance, moving time, elevation gain, speeds, heart rate
track.position_at(photo_times)        # where you were at each time (great-circle interpolation)
track.stays()                         # places you stopped, with gap bridging
```

Readers and writers need no dependencies (FIT is decoded from the public spec). Operations include
Kalman smoothing, thinning, resampling, splits and best efforts, camera clock-offset estimation for
photo geotagging, trips, travel modes, flights, time inside an area, border crossings, days per
country, merging recordings from several devices, and route comparison (Hausdorff, Fréchet,
corridor overlap, deviations).

## Privacy (`placewise.privacy`)

```python
from placewise import privacy

key = b"..."                          # at least 16 secret bytes, kept and reused
shared = privacy.apply(track, privacy.preset("public_share"), key)
```

Privacy zones whose cut points don't give away the hidden place, secret-length trimming, keyed grid
snapping, geo-indistinguishable noise, time coarsening, and an audit of what a track reveals. Every
tool documents what it does *not* protect against.

## Data

The base install is just the **world** pack (10 MB download, 43 MB on disk), installed on first
use. Everything else is a pack you add, by hand or on demand:

```
placewise data status                 # mode, installed packs and their size on disk, what auto mode fetches
placewise data mode                   # how packs arrive: manual (default), auto or locked
placewise data mode locked            # never download anything (written to placewise.toml)
placewise data mode auto --kinds country,parks,water   # auto mode may fetch these kinds of pack
placewise data install usa            # download, verify and install a pack (and any it requires)
placewise data list                   # installed and available packs, every version
placewise data update                 # newer versions (never automatic, never deletes)
placewise attribution                 # the installed packs' sources, licences and credits (--all, --short)
```

**Modes** (`data.mode` in `placewise.toml`, `PLACEWISE_DATA_MODE`, `placewise data mode`):

- **auto** (opt in with `placewise data mode auto`): the first lookup batch with points in the US installs `usa`, a point in
  Canada `can`, and so on, once, before the batch runs, with a log line naming the pack and its
  size. Only the kinds in `data.auto_packs` are fetched, by default `country` packs, the ones that
  change the main answer (city, county, metro area, postal code). Add `parks`, `water`,
  `notable` or `postal` to fetch those too (`PLACEWISE_DATA_AUTO_PACKS=country,parks`). A search
  that asks for a kind (`find("Banff", kinds="park", country="CA")`) fetches that kind's packs for
  its country (`can-parks`) even when it isn't in `auto_packs`. Installed packs are used straight
  away; a lookup that needs nothing new doesn't download anything (auto mode plans from the cached
  index, fetching a fresh one only when that is over a week old). Fetching a country pack does tell the download host which
  country you looked up; choose `manual` or `locked` if that matters to you.
- **manual** (the default): packs arrive only with `placewise data install`; the world pack still
  installs on first use. A lookup that a missing pack would improve logs once which pack to install.
- **locked**: never download anything, not even the index; use exactly what is installed (a
  missing world pack is an error). `--offline` and `data.offline = true` (the older spelling)
  mean locked whatever the mode. Servers and read-only deployments should run locked.

The default keeps the base lean: only the world pack until you install more. Auto mode with its
default kinds fetches only country packs, and only for the countries you look up. Sizes for the
2026.11 data (download / on disk): `usa` 38 / 96 MB, `can` 23 / 110 MB, `ind` 15 / 41 MB,
`usa-parks` 40 / 108 MB, `can-parks` 9 / 33 MB, `world-water` 25 / 46 MB, `world-parks` 0.1 / 0.6 MB;
`placewise data status` shows the current ones.

Everything placewise downloads lives in `~/.placewise/` unless configured otherwise (`--data-dir`,
`PLACEWISE_DATA_DIR` or `data.data_dir` in `placewise.toml`; `placewise data where` prints it).
Packs are memory-mapped and checksummed (format: `docs/pack-format.md`). Data sources are listed in
`src/placewise/sources/`, one JSON file per purpose (boundaries, places, regions, postal codes,
airports ...) giving the sources used in each region, and `ATTRIBUTION.md` is generated from them,
so an app that ships placewise data can link to that one file.

Packs are published as release assets of `amolvenkataraman/placewise-data` (`index.json` plus one
`.tar.xz` per pack); any copy of a release's files works as a mirror (`--index-url`, `data.mirrors`).

## Conventions

- Coordinates are WGS84 degrees, always in `(lat, lon)` order (GeoJSON uses `(lon, lat)`).
- Every function accepts scalars or numpy arrays and broadcasts; scalars in, plain floats out.
- Distances are kilometres unless a name ends in `_m`.
- English names only; standard coordinate systems only (no obfuscated ones like GCJ-02).

## Licence

The code is licensed under the [Apache License 2.0](LICENSE) (see also [NOTICE](NOTICE)). The data
packs keep their sources' licences (`ATTRIBUTION.md`); placewise's own curated datasets, in the
placewise-data repository, are CC BY 4.0.

## Disclaimer

placewise and its data packs are provided "as is" and "where is", with no warranty of any kind and
no legal liability for their use. Names, boundaries and other data may be wrong or out of date and
are not an official determination of any territory's status. See [DISCLAIMER.md](DISCLAIMER.md).

## Development

```
uv sync                 # creates .venv with the dev tools
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

Requires Python 3.10+. The runtime depends on numpy only; `pip install placewise[geodesic]` adds
GeographicLib for ellipsoidal distances. `packbuild/` (not shipped) turns public datasets into packs.
