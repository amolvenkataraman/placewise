# packbuild

Turns public datasets into pack layers (see `docs/pack-format.md`). Build-time only: it is not in
the wheel. Tests live in `tests/packbuild/` and never touch the network.

```
uv run python -m packbuild.world --version 2026.11     # writes ~/.placewise/packbuild/out/world-2026.11/
```

**Curated datasets** (country groups, regions, names and aliases, airports' cities) live in the
[placewise-data](https://github.com/amolvenkataraman/placewise-data) repository's `datasets/`
folder (CC BY 4.0). Clone it beside this repository (`../placewise-data`) or point
`$PACKBUILD_DATASETS` at its `datasets/` folder; `packbuild/datasets.py` resolves the path. The
generators (`python -m packbuild.country_groups`, `packbuild.regions`, `packbuild.cities` (cities and
`datasets/names/aliases.json`)) write the
offline copies the package ships into `src/placewise/constants/countries/`.

Downloads are cached once in `~/.placewise/packbuild/` (`packbuild.fetch.DEFAULT_CACHE`; set
`$PACKBUILD_CACHE` or pass `--cache-dir` to use another place) with a `<file>.json` sidecar holding
the URL, SHA-256, size and retrieval date; `--refresh` downloads again. Nothing downloaded is
committed.

## World pack

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `countries` | polygon | Natural Earth 1:10m admin-0 countries | public domain |
| `admin1` | polygon | Natural Earth 1:10m admin-1 states/provinces | public domain |
| `cities` | point | GeoNames cities1000 + admin1CodesASCII + countryInfo | CC BY 4.0 |
| `airports` | point | OurAirports airports.csv (large, medium, scheduled small) | public domain |
| `timezones` | polygon | the hand-drawn shapes of `datasets/timezones/world.json`; every unit's zone is the `tz` column of `countries` and `admin1` (see [Time zones](#time-zones)) | CC BY 4.0 + public domain |
| `country_facts` | point | one row per country (`iso:XX`, at its capital, else Natural Earth's label point): GeoNames countryInfo, timeZones and capitals; CLDR currency, conventions and date patterns; Wikidata driving side (`packbuild.country_profiles`) | CC BY 4.0, Unicode-3.0, CC0 |

**Names people type** (`packbuild.world_aliases`, for forward search's name index): `cities`,
`admin1` and `countries` carry pipe-separated `aliases` (English names, exonyms, nicknames, short
forms), `abbreviations` ("NYC", "Ont.", "U.S."), `former_names` ("Bombay", "Orissa", "Zaire") and,
on cities, `airport_codes` ("YYZ|YTO"), at most 12 per feature and none equal to its own name. They
come from placewise-data's `datasets/names/aliases.json` (curated: codes, short forms, nicknames,
former names, and GeoNames names to suppress; it also generates
`constants/countries/city_aliases.py`), India's former state and city names in
`datasets/names/ind.json`, and GeoNames alternateNamesV2 (streamed from the 205 MB zip): English
names that aren't nicknames, `abbr`, IATA codes attached to cities and English short names;
historic names only for cities of 100,000+ people and only where a curated dataset lists them, and
never a name another city of the same country has. `admin1` also gets `geonames`, Natural Earth's
GeoNames id for the unit, and `population` (`world.admin1_population`): the people of the GeoNames
cities in it (sections of cities left out), joined by that id through admin1CodesASCII or by name
in its country; null for units GeoNames doesn't have as admin-1 (England's counties, France's
départements). The name index ranks admin-1 units by it.

**City served** (`packbuild.served`): `airports.served_city` is the `cities` id of the city an
airport serves (YYZ -> Toronto, not Mississauga), from `datasets/airports/served.json` (curated, every
large airport and the medium scheduled ones in India, the US and Canada; the build checks each id,
name, country and that the city is within 100 km), else the nearby rule for any airport with an
IATA code: of the cities of its country within 60 km, the highest population / (km + 10)².

Attribution records (`placewise.model.Source`) are in `packbuild/sources/__init__.py`; building
them checks each licence against `placewise.constants.licences`.

Ids: `iso:CA`, `iso:CA-ON` where the ISO code is real and unique, otherwise Natural Earth's own
code (`ne:SOL`, `ne:BIH-4801`); `geonames:<id>`; `ourairports:<ident>`.

Natural Earth's default files draw borders de facto. Its per-worldview attributes (`ADM0_A3_XX`,
`FCLASS_XX`) are kept as str columns, and its 99 disputed areas, with every view's `ADM0_A3_XX`,
are the `worldviews` polygon layer (0.95 MB); see `docs/worldviews.md`.

## Time zones

Packs carry time zones as a **`tz` column on the admin layers they already have**
(`packbuild/timezones.py`), drawn from the curated tables in placewise-data's
`datasets/timezones/` (CC BY 4.0; registry id `placewise-timezones`), so `Result.tz` doesn't need
the share-alike timezone-boundary-builder data. 216 of tzdb's 247 countries have one zone: the
country is the zone. The rest follow admin lines, so `world.json` maps Natural Earth countries and
admin-1 units to IANA zones, `usa.json` states and Census counties (plus the Navajo Nation and
Annette Island from Census AIANNH, `uscensus` download `aiannh`), `can.json` provinces, census
divisions and subdivisions; each entry cites tzdb or the law it follows, and a few hand-drawn
boxes cover what no unit fits (Eucla, the western Aleutians, research stations, remote islands).

| Where | `tz` |
|---|---|
| world `countries`, `admin1` | the unit's own entry: a zone; `-` an entry with no zone (tzdb records none: the nearest-city rule answers); `""` no entry (an admin-1 unit takes its country's; a country split by its admin-1 units has none) |
| usa `counties`, can `csd` | the unit's resolved zone: its own entry, else its census division's (Canada), else its state's or province's |

A unit split along a line no pack draws has its zones joined by `|` (the first is the default):
the nearest GeoNames city inside the unit whose zone is listed decides. A split zone is never
passed down to a finer unit (the build fails), since the nearest-town rule searches the unit it
was given to. The **`timezones` layer** holds only the hand-drawn shapes and AIANNH areas (columns
`zone`, `zones`, `basis` = `shape`, `unit`, `within`, `country`); a pack whose table has none (can)
has no such layer. Nothing else copies a unit's outline (the old layer did: 19 MB in can, 7 MB in
world, 4 MB in usa). The build fails, listing every problem, on a zone missing from
`zoneinfo.available_timezones()`, a unit of the layer without an entry (full coverage), an entry
naming a unit the layer lacks or one of another country, an unknown source or a bad shape.

The engine (`placewise.engine._timezones`) reads the zone of the units it has already found, with
no polygon query of its own beyond the small shapes layer: the worldview's country's zone where it
reports a disputed area in a one-zone country; else, on agreed ground in a country pack's country,
a shape of that pack containing the point, else the `tz` of the county or subdivision the naming
rules found the point inside (not one it was only snapped to); else the world unit the admin answer
found (a shape of its country, else its admin-1 unit's entry, else its country's); else the nearest
city of the same country (as before). At sea beyond the territorial sea: none. Packs built before
the column (whose `timezones` layer copies every unit) are still read (`engine/_tz_legacy.py`).
India is one zone (Asia/Kolkata); with the de facto polygons it covers India-administered ground.
On the 2026.11 packs the column answers exactly as the copied polygons did (see the proof under
[Pack sizes](#pack-sizes)).

Known gaps (the unit is split, so the nearest city decides): Mexico's US-border municipios and
Bahía de Banderas, Pará (east/west), Sakha's districts, Broken Hill (Yancowinna). Not drawn:
Europe/Busingen, Australia/Lindeman.

## US pack (`usa`)

```
uv run python -m packbuild.us --version 2026.11        # writes ~/.placewise/packbuild/out/usa-2026.11/
```

Everything comes from the US Census Bureau (registry id `uscensus`, public domain), except the
postal city names of the ZIP Codes the Census files lack (GeoNames, `geonames`, CC BY 4.0):

| Layer | Kind | Source | Key columns |
|---|---|---|---|
| `states` | polygon | CB 2025 state 1:500k | `usps`, `statefp` |
| `counties` | polygon | CB 2025 county 1:500k + delineation list 1 (2023) + ACS 5-year B01003 | `name` with LSAD, `state`, `cbsa`, `csa`, `central`, `population` (ACS; ranks counties in the name index) |
| `places` | polygon | CB 2025 place 1:500k + 2025 gazetteer + SUB-EST2025 + ACS 2020-2024 B01003 + delineation list 2 | `lsad`, `class` (incorporated / cdp), `funcstat`, `state`, `population`, `population_source`, `principal`, `intpt_lat/lon` |
| `cbsa` | polygon | CB 2025 CBSA 1:500k + delineation lists 1 and 2 | `type` (metro / micro), `csa`, `counties`, `principal_cities` |
| `csa` | polygon | CB 2025 CSA 1:500k + delineation list 1 | `cbsas`, `counties` |
| `postal_cities` | polygon | the ZCTAs (below) whose postal city can name a locality | `postal_place` |
| `regions` | polygon | curated regions as unions of counties (see [Regions layer](#regions-layer-us-canada-and-india-packs)) | `kind`, `members`, `aliases`, `area_km2` |

The time zones are a `tz` column on `counties` (each county's zone, else its state's: [Time
zones](#time-zones)), and `timezones` holds the few areas no county fits (Navajo Nation, Annette
Island, the western Aleutians).

The ZIP Code areas themselves are the optional **`usa-zip`** pack (`python -m packbuild.us_zip
--version 2026.11`; pack.json `kind` postal, `covers` US, `requires` usa):

| Layer | Kind | Source | Key columns |
|---|---|---|---|
| `zcta` | polygon | CB 2020 ZCTA5 1:500k + 2025 gazetteer + ACS B01003 + ZIP Code Business Patterns 2023 + GeoNames US postal codes + 2020 ZCTA-to-place relationship | `aland`, `intpt_lat/lon`, `population`, `postal_city`, `postal_place`, `postal_source` |

With usa-zip installed a US lookup has `postal` and search finds ZIP Codes; without it `postal`
is empty for US points and everything else answers the same. The naming rules let a ZIP Code's
postal city stand for a CDP or unincorporated land in a metro county, so `usa` keeps
`postal_cities` (`packbuild/us_zip.py`): the ZCTAs, outlines unchanged, whose `postal_place` is a
place of the pack and whose box meets a metro county's box widened by 0.05° (past the rules' 1 km
shore snap); anywhere else the postal city never applies. 19,495 of 33,791 ZCTAs, 3.5 of 5.9 M
vertices, with only `id`, `name` and `postal_place`. On the 2026.11 packs, lookups without
usa-zip equal lookups with the old usa (ZCTAs inside) on 30,000 US points apart from `postal`.

Ids: `census:<GEOID>` for places and counties; `census:cbsa:<code>`, `census:csa:<code>` and
`census:zcta:<zcta>` for the rest, because those GEOIDs collide with each other and with county
GEOIDs (ZCTA 06085 is in Connecticut, county 06085 is Santa Clara); states are `iso:US-CA`, the
same id as the world pack's admin1. Member lists (`counties`, `cbsas`) are comma-separated codes.

- **Datum.** CB files are NAD83 (EPSG:4269), which `placewise.io.read_shapefile` refuses. NAD83 and
  WGS84 differ by 1-2 m in the US, well inside the 1:500k generalisation, so
  `uscensus.read_census_shapefile` accepts a geographic NAD83 .prj and reads the coordinates as
  WGS84 unchanged. Other datums (NAD27) and projected files are still refused.
- **Places** are incorporated places first, then CDPs (and Puerto Rico's comunidades and zonas
  urbanas, `class` "cdp"), so an incorporated place would win where both cover a point (none was
  found in 2025). `population` is the newest SUB-EST estimate where there is one (incorporated
  places and Urban Honolulu CDP, `population_source` "sub-est2025"), else the ACS 5-year estimate
  of table B01003 ("acs5y2024": every CDP, Paradise 185,913); 32,316 of 32,629 places have one
  (the Island Areas and a few inactive places don't). The Las Vegas Strip is in Paradise CDP, not
  Las Vegas city: names people use and Census names differ (`docs/naming.md`).
- **Populations** come from the ACS table-based summary file (`acsdt5y2024-b01003.dat`, 18 MB,
  every geography in one pipe-separated file keyed by GEO_ID), which needs no API key, unlike
  api.census.gov. Vintage 2020-2024; the 2021-2025 file is due in December 2026 (bump the URL).
- **Principal cities** are OMB delineation list 2 (July 2023, `list2_2023.xlsx`): 1,294 cities of
  935 CBSAs, CDPs among them (Paradise, Arlington VA, The Woodlands). `places.principal` is the
  CBSA code a place is a principal city of; `cbsa.principal_cities` lists the CBSA's place ids
  largest first (the file is alphabetical; OMB titles a CBSA by its largest principal city, so the
  first is the title's), leaving out the few not in the places layer. The naming rules read these
  instead of parsing CBSA titles.
- **Postal cities.** `zcta.postal_city` is the city USPS gives the ZIP Code's addresses (89109 Las
  Vegas, 94128 San Francisco, 11201 Brooklyn). USPS's City State file is copyrighted and sold per
  copy, and the HUD crosswalk needs a login, so the names come from ZIP Code Business Patterns
  2023 (`zbp23totals.zip`, public domain: the USPS city of the 34,954 ZIP Codes with a business,
  upper case without punctuation) and, for the ZIP Codes it lacks, GeoNames' US postal codes
  (`US.zip`, CC BY 4.0, 41,490 ZIP Codes, cached in `geonames-postal/` beside the others since
  GeoNames' dump has a `US.zip` too). Compared on the 33,791 ZCTAs: Business Patterns has 30,917,
  GeoNames 33,642; where both have one they agree on 30,876 (99.9%) once case and punctuation are
  ignored, and most of the 41 differences are newer names in Business Patterns (92509 Jurupa
  Valley, incorporated 2011, where GeoNames says Riverside; 33460 Lake Worth Beach). Public domain
  is preferred, so Business Patterns goes first: 30,917 ZCTAs take its name, 2,725 GeoNames', 149
  have none. `postal_place` is the census place the name means: a place of that name in the
  ZIP Code's state, preferring one the 2020 ZCTA-to-place relationship file
  (`tab20_zcta520_place20_natl.txt`) says overlaps the ZCTA (a state can have two places of a
  name), then incorporated, then the most people; names compare without case, accents, spacing or
  punctuation and with Saint/Mount/Fort as St/Mt/Ft ("MC LEAN" is McLean). 27,038 ZCTAs match a
  place; a matched name is shown in the place's spelling, else GeoNames' or title case.
  `postal_source` says which file named it. The `zcta` layer's sources are `uscensus` and
  `geonames` (`postal_cities`: `uscensus`, plus `geonames` should a kept ZCTA's name come from it).
- **ZCTAs** are the Census Bureau's areal approximation of USPS ZIP Codes. USPS publishes ZIP Codes
  as delivery routes, not areas; most addresses' ZIP matches their ZCTA but not all, PO-box-only
  ZIPs have no ZCTA, and unpopulated land is in none. ZCTAs are defined once a decade, so the
  2020 file is current. Polygons cost about 52 MB (26 MB of the archive; hence usa-zip); gazetteer
  points would be 2 MB, but the nearest internal point names the containing ZCTA only ~70% of
  the time near populated places, so the pack ships polygons (`uscensus.zcta_points` is the
  alternative).
- **Shoreline.** CB shapes are clipped to the shoreline: points in bays and coastal water fall in
  no county, place or ZCTA, and gazetteer internal points (computed from full TIGER/Line) can fall
  outside the clipped shape (San Francisco's is on the Farallon Islands).
- **Delineation.** OMB list 1 is an .xlsx; it is read with the standard library (zip + XML).

## Canada pack (`can`)

```
uv run python -m packbuild.ca --version 2026.11 --via service   # writes ~/.placewise/packbuild/out/can-2026.11/
```

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `provinces` | polygon | StatCan 2021 cartographic boundary file, provinces/territories (`lpr_000b21a_e`) | StatCan Open Licence |
| `cd` | polygon | ... census divisions (`lcd_000b21a_e`): counties, regional municipalities (Halton, Peel) | StatCan Open Licence |
| `csd` | polygon | ... census subdivisions (`lcsd000b21a_e`): municipalities (Milton, Toronto), reserves, unorganised areas; `tz` each one's time zone ([Time zones](#time-zones)) | StatCan Open Licence (+ CC BY 4.0 for `tz`) |
| `cma` | polygon | ... census metropolitan areas and agglomerations (`lcma000b21a_e`) | StatCan Open Licence |
| `fsa` | polygon | 2021 Census forward sortation area boundary file (`lfsa000b21a_e`) | StatCan Open Licence, with Canada Post's notice |
| `populated_places` | point | Canadian Geographical Names Database (NRCan), generic category "Populated Place" | OGL-Canada 2.0 |
| `regions` | polygon | curated regions as unions of CDs, CSDs or CMAs (see [Regions layer](#regions-layer-us-canada-and-india-packs)) | CC BY 4.0 + StatCan Open Licence |

Populations (`population`, null when StatCan suppresses the count) come from the census population
and dwelling count tables 98-10-0002-01 (provinces, CDs, CSDs), 98-10-0005-01 (CMAs/CAs) and
98-10-0019-01 (FSAs), joined on DGUID. Registry: `statcan-boundaries-2021`, `statcan-fsa-2021`,
`statcan-population-2021`; credit lines are the "Adapted from Statistics Canada ..." notice the
licence requires for value-added products.

Ids are `statcan:<UID>`: PRUID (`statcan:35`), CDUID (`statcan:3524`), CSDUID (`statcan:3524009`),
CMAPUID (`statcan:35535`: province + CMA code, so Ottawa - Gatineau is two features, `35505` and
`24505`, both named "Ottawa - Gatineau" and carrying the whole CMA's population; `name_full` keeps
"(Ontario part / partie de l'Ontario)") and CFSAUID (`statcan:M5V`). Province codes (`ON`, `QC`,
...) are the SGC 2021 alpha codes. A CSD's `cduid` is its CSDUID's first four digits.

**Downloads.** The zips live on www12.statcan.gc.ca, which answers scripted clients with a
Cloudflare browser check (HTTP 403, seen November 2026), so `--via files` (the default) only works
where that check lets you through. `--via service` reads the same 2021 cartographic files from
Statistics Canada's own ArcGIS REST service (geo.statcan.gc.ca, layers `lcsd000b21s_e` etc.: the
`s` is StatCan's file-name code for "services"), in pages of Esri JSON in the native projection,
cached under `~/.placewise/packbuild/<layer>/` with a `<layer>.json` sidecar. The service's gateway gives
up after 60 s, which the largest boundaries don't fit in at full resolution (Ontario alone times
out; Nunavut has 190,000 km of coastline), so requests are planned by perimeter (`SHAPE_Length`):
OBJECTID ranges of at most 8,000 km, features over 10,000 km alone, and features over 15,000 km
generalised by the service itself (`maxAllowableOffset`, about 1 m per 600 km of perimeter, 25 to
400 m in practice). The sidecar's `generalised_m` lists them; they are the big northern and coastal
units (Nunavut, NWT, Labrador, Nord-du-Québec, the BC coast, Ontario's Hudson Bay shore), whose
length is mostly coastline; their borders, too, can move by up to the offset. `--via files` reads
every feature at full resolution.

**Projection.** StatCan publishes the boundary files only in Statistics Canada Lambert (EPSG:3347,
NAD83), never in longitude/latitude, and `placewise.io.read_shapefile` refuses projected files.
`packbuild/projection.py` implements Lambert conformal conic (2SP, IOGP Guidance Note 7-2) on GRS 1980;
it is tested against the guidance note's worked example and against vertices StatCan's map service
returns in both EPSG:3347 and EPSG:4269 (agreement to ~1e-9°). The `.prj` of each shapefile is
checked against the EPSG:3347 parameters. NAD83(CSRS) is used as WGS84 without a datum shift: they
differ by 1-2 m in Canada, below the simplification.

**Simplification.** The cartographic files are clipped to the shoreline but not generalised (a
vertex every few metres), so rings are simplified with Douglas-Peucker at 10 m, in Lambert metres,
before unprojecting (`--tolerance-m`, 0 to keep everything). Each feature is simplified on its own,
so neighbours' shared borders can differ by up to the tolerance; rings smaller than it (rocks,
islets) are dropped, but a feature never loses its last ring.

**Named places.** `populated_places` is CGNDB's national CSV (`cgn_canada_csv_eng.zip`, 16 MB,
refreshed weekly; registry `nrcan-cgndb`) cut to populated places: hamlets (Lake Louise), rural
communities (Field), towns, and the urban communities, neighbourhoods and boroughs inside
amalgamated cities (Scarborough, Kanata, Malton, Port Credit, Ville-Marie), without railway
points, post offices, stations and former or vacated places (`cgndb.DROPPED`): 26,123 of 29,780.
Columns: `id` (`cgndb:<CGNDB ID>`), `name` (as decided, English or French), `generic` (the generic
term), `province`, `scale` ("Relevance at Scale", the map scale from which the name shows: a
prominence). It comes from NRCan, not StatCan, so the www12 browser check doesn't block it.
StatCan's population centres and designated places were checked and contain no Lake Louise.

**Metro regions.** CMAs are StatCan's commuting-based units, but the GTHA (Greater Toronto and
Hamilton Area) is not a CMA: Toronto, Hamilton and Oshawa are separate CMAs, Burlington (Halton) is
in the Hamilton CMA and the Toronto CMA takes in part of Simcoe County. So the GTA, GTHA and Golden
Horseshoe are curated as unions of census divisions (and one CSD) in the `regions` layer below.

**Not here:**

- *Postal codes.* FSAs are the first three characters of the postal code; these are StatCan's
  census FSAs (one per dissemination area, from the postal codes respondents reported), which can
  differ from Canada Post's delivery areas (the CN Tower is in census FSA M5J although its postal
  code is M5V). Full six-character postal codes and their coordinates are Canada Post data and are
  not open data in Canada; placewise uses no postal-code-to-coordinate dataset.

## India pack (`ind`)

```
uv run python -m packbuild.india --version 2026.11     # writes ~/.placewise/packbuild/out/ind-2026.11/
uv run python -m packbuild.india --version 2026.11 \
    --pincode-boundaries All_India_pincode_Boundary-19312.geojson --pincode-directory pincode.csv
```

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `states` | polygon | LGD states as unions of PIN area pieces (`lgd:state:<code>`, `iso`, `kind`, `aliases`) | GODL-India + CC BY 4.0 |
| `districts` | polygon | LGD districts the same way (`lgd:district:<code>`, `lgd_name`, `census2011`, `aliases`: former names first) | GODL-India + CC BY 4.0 |
| `cities` | polygon | urban local bodies (ULBs) drawn as their PIN areas (`lgd:ulb:<code>`, `official_name`, `type`, `members`, `local_name`) | GODL-India + CC BY 4.0 |
| `pincodes` | polygon | All India Pincode Boundary (Department of Posts, 2025), district and state joined from the directory, plus the crosswalk (`lgd_district`, `lgd_subdistrict`, `city`) | GODL-India |
| `post_offices` | point | All India Pincode Directory (Department of Posts): offices whose coordinates lie in or within 2 km of their own PIN area | GODL-India |
| `neighbourhoods` | point | post offices inside cities, named without their type words ("Koramangala S.O" -> Koramangala) | GODL-India |
| `regions` | polygon | curated regions as unions of PIN areas grouped by district or LGD unit (see [Regions layer](#regions-layer-us-canada-and-india-packs)) | CC BY 4.0 + GODL-India |

Every polygon layer but `regions` has `india_view_only`; the derived layers have `area_km2`. The
build takes about 100 s and 1.7 GB.

Registry: `indiapost-pincode-boundary`, `indiapost-pincode-directory`, `lgd-directory`,
`placewise-names` (placewise-data `datasets/names/ind.json`), `naturalearth`. Ids: `pin:560001`;
`indiapost:<pincode>:<office name>` (`#2`, `#3`, ... when a name repeats under one PIN code).
`state_code` is ISO 3166-2 after the 2023 change (`IN-TS`, `IN-OD`, `IN-CG`, `IN-UK`), so it
matches `iso:IN-KA`-style admin1 ids; district and state names stay upper case as published.

- **Downloads.** data.gov.in refused or blocked scripted requests in November 2026 (Akamai
  "503"/connection refused) and the boundary resource was reported returning 404 in May 2026; the
  directory's API needs a free key; AIKosh's copies go through a click-through. So each registry
  file names a mirror: the boundary GeoJSON pinned to a commit of a GitHub repository (the same
  bytes, git blob `6a73f2df`, are in three unrelated repositories) and the directory CSV as taken
  from data.gov.in in May 2024. GODL allows that redistribution. A file downloaded by hand from
  data.gov.in replaces its mirror (`--pincode-boundaries`, `--pincode-directory`; the directory's
  API export with lower-case headers reads the same).
- **Join.** A PIN area's `district`/`state` is the one most of its offices are filed under (ties:
  head office, then sub, then branch office, then by name). PIN areas cross district lines, so it
  is the postal answer, not an administrative one.
- **Coordinates.** Directory coordinates are kept only when both are plain numbers inside a box
  round India (6-38 N, 68-98 E); "NA", the 1/1 placeholder and values with stray characters (a
  trailing "-") are dropped, not repaired. GeoJSON whose `crs` is not WGS84 is refused.
- **Offices against their PIN areas.** Many directory coordinates are wrong: on the 2026.11
  build only 91,016 of the 143,571 offices with usable coordinates (63.4%) lie inside their own
  PIN area, 41,573 lie in another PIN area (often another district or state) and 1,577 in none
  (outside India, some in neighbouring countries, or off the coast). So an office keeps its point
  only if it is inside its own PIN polygon or within 2 km of its boundary
  (`indiapost.OFFICE_BUFFER_KM`, `keep_placed_offices`); the rest, and the 283 offices whose PIN
  code has no polygon, are left out of `post_offices`, and the build logs each count. That kept
  100,138 offices: the 91,016 inside, which are now 90.9% of the layer, and 9,122 within 2 km.
  Why 2 km: PIN areas are generalised delivery zones and offices often sit on the road that bounds
  one, so a strict inside test drops good points (4,109 lie within 500 m outside, 6,342 within
  1 km); past a couple of km the point is inside a neighbouring area, and the count keeps rising
  with no clear break (13,961 within 5 km, 19,218 within 10 km), which is the signature of points
  misplaced by whole areas rather than metres. The test runs on placewise's own pack geometry
  (`PolygonLayer.contains`, and `nearest_edge_km` to the office's own area for offices near
  its bbox; distances exact on the sphere): the PIN areas are written to a temporary pack first;
  the check takes about 7 s of the build's ~16 s. Ids keep
  the directory's numbering, so a left-out office leaves a gap rather than renumbering the rest.
- **LGD.** The Local Government Directory's daily reports (states, districts, sub-districts, ULBs,
  village -> PIN and ULB -> PIN tables) are GODL-India on data.gov.in, which blocks scripted
  downloads; the registry names a community mirror's monthly 7z archives, read with the standard
  library (`packbuild/ind/sevenzip.py`; the newest day of the month is used).
- **Crosswalk** (`packbuild/ind/crosswalk.py`). A PIN area's district and sub-district are those
  most of its LGD villages are in (17,143 areas), else the directory's district matched to LGD by
  name and the curated former names (2,039), else its ULB's or its neighbours'. It belongs to a
  city when it is at most 40 km2 and LGD lists it for that ULB (rows listing one PIN code for
  more than 3 ULBs are office addresses, ignored), the curated dataset seeds it (Bengaluru as the
  former BBMP area: LGD's five 2025 corporations have no PIN rows yet; Noida and Navi Mumbai,
  whose LGD rows are empty or wrong), or it is urban (no India Post branch office, or no LGD
  village: LGD lists revenue villages in Mumbai and Ahmedabad too) and touches the city's listed
  areas in the same PIN block (first 4 digits: Mumbai Suburban's 4000xx joins Mumbai, not
  Thane), then the same district; rural areas a city surrounds (75% of their border) join it.
  Delhi's three former corporations are one city (`lgd:ulb:276402`, the 2022 reunification).
  Cities are postal approximations: big fringe PIN areas stay out (Mumbai is 280 km2 of BMC's
  437, Ahmedabad 217 of 505; Bengaluru 767 of BBMP's 741).
- **De facto pieces** (`packbuild/ind/defacto.py`). PIN areas follow India's official boundary
  (Gilgit and Skardu are in 194401, filed under Ladakh; Aksai Chin in 194101). Each PIN area
  reaching ground a neighbour administers in Natural Earth's de facto countries is cut along it
  (`packbuild/ind/clip.py`); the piece there is `pin:<code>#india-view` (`india_view_only`), and a
  derived unit with such pieces has a `#india-view` row too (Ladakh's covers 102,000 km2, Jammu
  and Kashmir's 11,900). The engine shows them only under the IN worldview. 320 of 19,312 PIN
  areas are cut, most by slivers where generalised borders overlap; Siachen Glacier (Natural
  Earth's nobody's unit) is not cut, as placewise answers it India de facto.
- **Accuracy**, against references checked locally and never shipped (122,832 random land points):
  the state agrees with geoBoundaries IND ADM1 (DataMeet, India's view) at 99.71% of points,
  0.14% fall in no state (coast); the district agrees with geoBoundaries ADM2 (2021) at 85.4% of
  the 108,784 points whose 2021 district name is still an LGD name (PIN areas cross district
  lines; districts split since 2021 count as misses).

**Not here:**

- *Surveyed state and district polygons.* The layers above are PIN-area unions; no surveyed
  source passed the licence gate. The Survey of India's
  Administrative Boundary Database is free but needs an account and an order, and its portal
  allows boundary files for consultative, research and education use. The National Water Data
  Portal republishes it without an account (`packbuild/sources/nwdp.py` reads its attribute
  schema, LGD codes included), but under "Other (Open)" with a copyright policy that excludes
  third-party material, and its SHP and GeoJSON are projected (EPSG:7755, refused; its KMZ is
  WGS84). geoBoundaries' India ADM1 is CC BY 2.5 India (not an accepted licence) and ADM2 is
  ODbL (share-alike pack only); LGD/Bharatmaps and Bhuvan layers carry no licence; GADM is denied.
  `--states`/`--districts` are refused until `boundaries.json` lists an `nwdp-soi-boundaries` entry for `ind`.
  Survey of India boundaries show India's official view, including areas India claims that other
  countries administer; Natural Earth's world admin1 is de facto.
- *Census 2011 towns.* The Town Directory has no coordinates and Wikidata has few census towns
  with coordinates; GeoNames in the world pack covers towns (the city score names a point in no
  `cities` polygon).

## Regions layer (US, Canada and India packs)

Each country pack ends with a `regions` polygon layer: the curated regions of
placewise-data's `datasets/regions/{usa,can,ind}.json` (CC BY 4.0, `datasets/LICENSE.md` there; read
from a checkout beside this repository or `$PACKBUILD_DATASETS`, see `packbuild/datasets.py`; registry id
`placewise-regions`), each drawn as the union of its `members`, which are features of the same
pack. `packbuild/regions_layer.py` builds it; every country builder calls it last.

| Column | |
|---|---|
| `id` | `region:gta`, `region:sf-bay-area`, `region:delhi-ncr` ... (the dataset id) |
| `name`, `short_name` | "Greater Toronto Area", "GTA" |
| `kind` | `metro` (OMB MSA/CSA, StatCan CMA), `official-planning` (an area a public body plans or governs as one: ABAG, Metrolinx, the NCR Planning Board), `vernacular` (a name in common use, drawn with official units) |
| `country` | ISO 3166-1 alpha-2 |
| `members` | comma-separated member ids: `census:06075`, `statcan:3520`, `pin:110001` |
| `aliases` | pipe-separated |
| `area_km2` | the union's area on the sphere |

Rows are smallest first, so `query` returns the most specific region and `query_all` every region
of a point (CN Tower: GTA, GTHA, Golden Horseshoe). Regions overlap freely.

- **Members.** US regions are counties (`census:<GEOID>`: the July 2023 OMB delineation for
  metros, ABAG's nine counties for the Bay Area); Canada regions are census divisions, subdivisions
  or CMAs (`statcan:<UID>`). India has no openly licensed district polygons (see the India pack),
  so an India region lists the districts its definition names (`districts`, spelled as the India
  Post directory spells them) and its members are the PIN areas filed under them, or LGD units
  (`lgd_units`: `district:<code>`, `subdistrict:<code>`) and its members are the PIN areas the
  crosswalk puts in them (the Mumbai Metropolitan Region at taluka level). A PIN area can cross a
  district line, so those outlines are the postal approximation of the units.
- **Build-time checks.** A member missing from the pack's layers, a region with no members, or
  (India) members that are not exactly the PIN areas of the listed districts or LGD units fail the build with
  every problem listed: fix the dataset, never the build.
- **Union.** No geometry library: member rings are cut into directed edges, edges two members
  share (once each way) are dropped and the rest stitched into simple rings. Removing a pair of
  coincident edges changes no point's even-odd count, so the union answers exactly as its members'
  rings would, without the internal borders. Census and India Post boundaries share their borders'
  vertices, so their unions come out clean (the NCR's 520 PIN areas make 11 rings). StatCan layers
  are simplified per feature, so simplified neighbours overlap or gap by up to 10 m, and under
  even-odd an overlap would fall outside the region; the Canada build therefore keeps the members'
  rings unsimplified as it reads them (statcan's `raw`), dissolves them and simplifies the union once.
- **Location search.** `packbuild.regions` also generates `constants/countries/regions.py` from the
  same files. A region with `search_as` (the GTHA, the Delhi NCR core, the Bengaluru Metropolitan
  Region) has no entry there: location search reads its names as the region it names.

## Water pack (`world-water`)

```
uv run python -m packbuild.water --version 2026.11                  # writes ~/.placewise/packbuild/out/world-water-2026.11/
uv run python -m packbuild.water --version 2026.11 --no-hydrolakes  # Natural Earth lakes only (12 MB pack)
```

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `marine` | polygon | Natural Earth 1:10m `geography_marine_polys`: 294 named seas, gulfs, bays, straits, ocean halves | public domain |
| `lakes` | polygon | HydroLAKES v1.0 lakes of 10 km² or more (`--min-lake-km2`), simplified to 30 m (`--tolerance-m`), named from Natural Earth, then Wikidata (CC0), then HydroLAKES; plus Natural Earth's lakes (and NA/Europe supplements) HydroLAKES doesn't cover | CC BY 4.0, public domain |
| `rivers` | polygon | Natural Earth 1:10m river centerlines + NA/Europe supplements, as zero-area polygons (each line out and back, so boundary distances measure the line) | public domain |

Columns: `id` (`wikidata:Q...` where unique, else `ne:<ne_id>` / `hydrolakes:<Hylak_id>`), `name`,
`type`, `wikidata`, `aliases` (pipe-separated), `area_km2` (polygons; rows smallest first),
`source` (lakes: `hydrolakes` / `naturalearth`, which sets the shore margin), `scalerank` (rivers).
Sources live in `packbuild/sources/water/` (registry `sources/water.json`).

- **Why a separate pack.** HydroLAKES makes it tens of MB, as big as the world pack (35 MB), and
  many users never need water; it rebuilds on its own schedule; and HydroLAKES' "don't redistribute
  in the original format" request stays scoped to the pack that carries a derivative of it. The
  Natural-Earth-only build is 12 MB (rivers 7.7, lakes 2.5, marine 1.5).
- **HydroLAKES download.** The 820 MB zip holds polygons largest first, so the build reads the
  zip's central directory by HTTP range request, fetches the .dbf (52 MB) and .shx, and inflates
  the .shp only up to the end of the last record kept (`sources/water/ranged_zip.py`): about
  220 MB in all at 10 km² (16,689 lakes); 1 km² (185,181 lakes) would need ~350 MB more.
- **Names.** HydroLAKES names 1,837 of its 16,689 lakes of 10 km²+. Natural Earth lakes covering an
  outline give it their name and Wikidata id (and are dropped); Wikidata lakes with an English
  Wikipedia article whose point falls inside name more (Dal Lake); unnamed outlines are dropped.
  HydroLAKES' `Country` (the outflow's) is never used.
- **Rejected:** Marine Regions IHO Sea Areas (CC BY-NC-SA 4.0) and HydroRIVERS (HydroSHEDS v1
  licence); both ids are in `constants.licences.DENIED_SOURCES`. See `docs/water.md`.

## Park packs (`usa-parks`, `usa-parks-local`, `can-parks`, `eur-parks`, `world-parks`)

```
uv run python -m packbuild.parks usa usa-local can eur world --version 2026.11
```

NPS, USFS and PAD-US 4.1 (US), CPCAD (Canada) and the EEA's Nationally designated areas (37
European countries) as one polygon layer per tier, Wikidata points elsewhere; the US's local parks
(`parks_local`, tier 4) are the optional `usa-parks-local` pack, whose pack.json says `kind` parks,
`covers` US, `requires` usa-parks. `eur-parks` is optional too: `kind` parks, `covers` the
countries with sites (its name names no country: `constants.packs.MULTI_COUNTRY_REGIONS`, which
also lets the source registry list sources under `eur`). Tiers, ids, sources and gaps in
`docs/parks.md`.

## Notable pack (`world-notable`)

```
uv run python -m packbuild.notable --version 2026.11   # writes ~/.placewise/packbuild/out/world-notable-2026.11/
```

One point layer, `notable`: famous places from Wikidata (CC0), ranked by QRank page views (CC0).
Registry `sources/notable.json` (`wikidata`, `qrank`).

| Column | |
|---|---|
| `id` | `wikidata:Q...` |
| `name`, `aliases` | English label; English aliases and short names, `|`-separated, at most 6 (`sources/notable/aliases.py`: short forms like "UW" first, web addresses and the place's own codes dropped; "X railway station" also "X station") |
| `kind` | `airport`, `station`, `university`, `campus`, `stadium`, `museum`, `religious_site`, `bridge`, `park`, `beach`, `landmark`, `viewpoint`, `building` (`placewise.constants.notable.KINDS` maps each to a `PlaceKind`) |
| `fame` | 0..1: the place's percentile within its kind among the pack's places, averaged with its percentile within (kind, country) |
| `country` | ISO alpha-2 from Wikidata P17 when it names exactly one country, else "": informational only, never used to say where a place is (the boundary layers and the worldview do that) |
| `sitelinks` | Wikimedia articles about it |
| `iata`, `icao`, `ipeds`, `aishe`, `station_code` | external ids where Wikidata has them (station codes: Indian Railways, Amtrak, VIA Rail, else P296; upper case) |

- **Kinds.** `sources/notable/kinds.py` is the class allowlist: one SPARQL query per kind lists the
  instances of its root classes or their subclasses with a coordinate, an English label and a
  sitelink, never dissolved, demolished or closed; protected areas are left to the park packs and
  university faculties out. An item of several kinds takes the first in the list (the Eiffel Tower
  is a landmark, not a viewpoint; a cricket ground is a stadium, not a park). Airports need an
  IATA code (scheduled service); airports named for an air force, air base or the military are
  dropped everywhere.
- **Downloads.** The queries run on QLever's Wikidata endpoint (WDQS times out on classes this
  big; the Wikidata API rate-limits) as TSV, about 110 MB for all kinds, each cached with its
  sidecar in `notable-<kind>/wikidata`; a cached result whose sidecar names another query is
  fetched again. QRank is pinned to one dated file (2026-11-15, SHA-256 in the registry notes);
  QRank keeps only its three newest, so rebuilds read the cached copy.
- **Selection** (`sources/notable/rank.py`), 2026.11: 881,484 candidates; a floor of 1,000 page
  views a year (200 in India, the US and Canada) leaves 239,045; places with the same name key
  within 300 m are merged (a station and its building; the subway's "Union" and the railway's
  "Union Station"), the most famous keeping the others' names as aliases; then, per 16 km
  equal-area cell, the 5 most famous of each kind (12 in India, the US and Canada), plus every
  place at fame 0.98+ and every university, campus and airport: 177,373 places, 39 MB (the layer
  22 MB, the name index 18 MB; the budget is 40 MB); the build takes about 65 s and 1 GB from the
  cache. Viewpoints are all landmarks too, so none keeps that kind.
- **Lookups** (`placewise.engine._notable`): `Result.near` lists up to 3 notable places after the
  cities and parks, each only within the reach its fame gives (0.99+: 2 km, 0.9+: 1 km, else
  300 m): the 3 best by `fame x (1 - distance / reach)`, listed nearest first. Airports
  (`Result.airport`) and places already named in `within` or `near` are left out. The label never
  changes.
- **Gaps.** Items without an English label (many Indian and Japanese stations have only local
  labels; Wikidata's `mul` labels are not read); India's universities without coordinates (only
  4,756 of 24,285 Wikidata items with an AISHE code have one); outlines (campuses, airports and
  stadiums are points); station complexes are merged only when their names match.

## Pack sizes

Installed size on disk (`du`, MB) of the 2026.11 packs built from the same sources before and after
grids were cut to each layer's extent, time zones moved onto the admin layers, and the ZIP Code
areas and US local parks became optional packs:

| Pack | Before | After | |
|---|---|---|---|
| `world` (the base install) | 56.8 | 49.6 | timezones 7.0 -> 0.1, grids 3.5 -> 2.3 |
| `usa` | 101.2 | 70.5 | zcta 52.4 -> postal_cities 30.9, timezones 4.0 -> 0.2, grids 6.6 -> 1.0 |
| `usa-zip` (optional) | - | 53.3 | the ZCTAs and their name index |
| `can` | 113.8 | 89.6 | timezones 19.8 -> 0 (the `tz` column on csd, cd, provinces), grids 5.5 -> 0.4 |
| `usa-parks` | 121.1 | 63.6 | parks_local moved out; grids 17.6 -> 1.0 (+1.5 in usa-parks-local) |
| `usa-parks-local` (optional) | - | 42.7 | parks_local and its name index |

world + usa + can + ind: 348 -> 286 MB (ind unchanged at 76.5 here; rebuilt with cut grids it loses
about 4 MB more). The grid index was the fixed cost of every polygon layer: a world-wide grid of
1° cells is 0.78 MB whatever the layer holds (0.5°: 3.1 MB, 0.25°: 12.4 MB). A grid now spans the
layer's extent, so a one-feature layer's is 0.5 KB, and the whole fixed cost of a small pack (one
polygon layer, name index, pack.json; 37 files) is 10 KB of data, 188 KB on disk with 4 KB blocks
(it was 0.94 MB at 1°, 12.3 MB at 0.25°). Across the 2026.11 packs grids went from 57 to 10 MB.

**Same answers.** 32,816 points (9,000 near US and 6,000 near Canadian GeoNames places, 7,800
uniform over the US, Alaska and Canada, 8,000 near other places, 2,000 anywhere, and the time-zone
e2e points) were looked up with the old code on the old packs and the new code on the new ones
(`ind` the same pack for both, read through the new reader's old-grid path):

- world alone: every field identical (28,980 points with a zone).
- world + usa + usa-zip + can + ind: identical, `Result.sources` naming `usa-zip/zcta` for
  `postal`, except that on 7 Canadian coastal points the zone (the same zone) is credited to
  `can/timezones:polygon` instead of `world/timezones:split`: they lie in a subdivision but outside
  the province's outline (the layers are simplified apart), which the copied polygons missed.
- without usa-zip: the same, less `postal`.
- world + usa + usa-zip + usa-parks + usa-parks-local: identical (`usa-parks-local/parks_local`
  in sources); without usa-parks-local the same less the local parks in `within`.

## Name index (every pack)

Every builder ends with `write_pack(..., names=names.for_pack(<pack>, layers))`: the pack's
`names/` directory (`docs/pack-format.md`, "Name index") that forward search reads. What goes in
is data, one `LayerNames` per layer in `packbuild/name_specs.py`: the official name columns,
pipe-separated `aliases` (short capitals such as "GTA" become abbreviations; columns a build lacks
are skipped, so world `aliases` columns are picked up as soon as they exist), former names, exact
codes (columns or templates such as `CA-{code}`, plus id prefixes such as `iso:` whose remainder
is a code), name suffixes to drop (India Post's "S.O", "B.O"), a label point for polygon layers
(Census `intpt_lat/lon`) and a rank on one scale across packs: populated places, counties, census
divisions and admin-1 units by population, CGNDB places by their scale and generic term (a
community or neighbourhood shown at 1:1.2M ranks like a town). Ids are always indexed. A layer of mixed
kinds names a `kind_column` and maps its values to PlaceKinds (`kind_values`): world-notable's
`kind` column, so a museum is found as a building and a station as a station; its rank is
0.15 + 0.7 x (fame - 0.5) / 0.5 for fame 0.5+, its codes IATA, ICAO, station codes and the bare
QID.

## Releasing data

Packs are published as GitHub release assets of `amolvenkataraman/placewise-data` (no data in its
git history; see its README). placewise's default index URL is that repository's
`releases/latest/download/index.json`, so **every release must list every pack**: an unchanged
pack is released again under the new tag.

```
# 1. build the packs (each writes ~/.placewise/packbuild/out/<name>-<version>/)
uv run python -m packbuild.world --version 2026.11
uv run python -m packbuild.us --version 2026.11

# 2. prepare: verify, archive, index (nothing is uploaded; prints the gh command it would run)
uv run python -m packbuild.release \
    --packs ~/.placewise/packbuild/out/world-2026.11 ~/.placewise/packbuild/out/usa-2026.11 \
    --out ~/.placewise/packbuild/release/2026.11

# 3. test the release directory as placewise would use it
uv run placewise --data-dir /tmp/pw-test \
    --index-url file://$HOME/.placewise/packbuild/release/2026.11/index.json data install world
uv run placewise --data-dir /tmp/pw-test \
    --index-url file://$HOME/.placewise/packbuild/release/2026.11/index.json data verify

# 4. publish (needs both the flag and the environment switch; uses gh's login)
PLACEWISE_ALLOW_PUBLISH=1 uv run python -m packbuild.release \
    --packs ~/.placewise/packbuild/out/world-2026.11 ~/.placewise/packbuild/out/usa-2026.11 \
    --out ~/.placewise/packbuild/release/2026.11 --publish [--tag 2026.11]
```

`packbuild.release.prepare_release(pack_dirs, out_dir)` re-hashes every pack (`open_pack(verify=True)`)
and refuses a pack name given twice, a pack schema other than the index's, a directory not named
`<name>-<version>`, a source id missing from the registry, and a share-alike source
(`placewise.constants.licences.SHARE_ALIKE`) in any pack whose name doesn't end in `-sa`
(`placewise.constants.packs.SHARE_ALIKE_SUFFIX`): share-alike data ships only in its own packs. It
writes into `--out`:

| File | |
|---|---|
| `<name>-<version>.tar.xz` | `placewise.packs.archive`: byte-for-byte reproducible from the pack's contents |
| `index.json` | `write_index`: relative URLs, so the directory is a complete mirror |
| `ATTRIBUTION.md` | `attribution.render_markdown(only=...)`: the disclaimer, then just the sources these packs use |
| `DISCLAIMER.md` | a copy of the repository's, which `ATTRIBUTION.md` links to |
| `SHA256SUMS` | for `sha256sum -c` (every asset above) |
| `release-notes.md` | the release description (`--notes-file`), not an asset |

`publish(plan, repo=..., tag=None, dry_run=True)` builds `gh release create <tag> --repo <repo>
--title "placewise data <tag>" --notes-file release-notes.md --latest <assets>`; the tag defaults to
the newest pack version. It only prints the command unless `dry_run=False` and
`PLACEWISE_ALLOW_PUBLISH=1`.

Before the first real release: placewise downloads anonymously, so the data repository must be
public (assets of a private repository's releases need a token). GitHub caps each release asset
at 2 GiB.
