# packbuild

Turns public datasets into pack layers (see `docs/pack-format.md`). Build-time only: it is not in
the wheel. Tests live in `tests/packbuild/` and never touch the network.

```
uv run python -m packbuild.world --version 2026.11     # writes .cache/packbuild/out/world-2026.11/
```

**Curated datasets** (country groups, regions, city aliases) live in the
[placewise-data](https://github.com/amolvenkataraman/placewise-data) repository's `datasets/`
folder (CC BY 4.0). Clone it beside this repository (`../placewise-data`) or point
`$PACKBUILD_DATASETS` at its `datasets/` folder; `packbuild/datasets.py` resolves the path. The
generators (`python -m packbuild.country_groups`, `packbuild.regions`, `packbuild.cities`) write the
offline copies the package ships into `src/placewise/constants/countries/`.

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
| `country_facts` | point | one row per country (`iso:XX`, at its capital, else Natural Earth's label point): GeoNames countryInfo, timeZones and capitals; CLDR currency, conventions and date patterns; Wikidata driving side (`packbuild.country_profiles`) | CC BY 4.0, Unicode-3.0, CC0 |

Attribution records (`placewise.model.Source`) are in `packbuild/sources/__init__.py`; building
them checks each licence against `placewise.constants.licences`.

Ids: `iso:CA`, `iso:CA-ON` where the ISO code is real and unique, otherwise Natural Earth's own
code (`ne:SOL`, `ne:BIH-4801`); `geonames:<id>`; `ourairports:<ident>`.

Natural Earth's default files draw borders de facto. Its per-worldview attributes (`ADM0_A3_XX`,
`FCLASS_XX`) are kept as str columns so a worldview choice can be offered later.

## Time zones

The world pack carries no time-zone polygons. The usual source, timezone-boundary-builder, is
built from OpenStreetMap and is ODbL (share-alike), and share-alike data may only go in the
separate share-alike packs (`placewise.constants.licences.SHARE_ALIKE`; named `<name>-sa`), never in
`world`.

Plan:

- **Now:** every GeoNames city carries its IANA zone (`cities.timezone`). A point's zone is the
  zone of the nearest city *in the same country* (country from the `countries` polygon), so a
  point near a border doesn't borrow the neighbour's zone. Good enough for almost all populated
  places; wrong in sparse areas cut by a zone line (e.g. parts of the US Midwest, Russia, Brazil).
- **Later:** zone polygons arrive with the OSM-based share-alike pack, with the ODbL
  derived-database offer that licence requires. When it is installed, polygons win; the
  nearest-city rule stays as the fallback.

## US pack (`usa`)

```
uv run python -m packbuild.us --version 2026.11        # writes .cache/packbuild/out/usa-2026.11/
```

Everything comes from the US Census Bureau (registry id `uscensus`, public domain):

| Layer | Kind | Source | Key columns |
|---|---|---|---|
| `states` | polygon | CB 2025 state 1:500k | `usps`, `statefp` |
| `counties` | polygon | CB 2025 county 1:500k + delineation list 1 (2023) | `name` with LSAD, `state`, `cbsa`, `csa`, `central` |
| `places` | polygon | CB 2025 place 1:500k + 2025 gazetteer + SUB-EST2025 | `lsad`, `class` (incorporated / cdp), `funcstat`, `state`, `population`, `intpt_lat/lon` |
| `cbsa` | polygon | CB 2025 CBSA 1:500k + delineation list 1 | `type` (metro / micro), `csa`, `counties` |
| `csa` | polygon | CB 2025 CSA 1:500k + delineation list 1 | `cbsas`, `counties` |
| `zcta` | polygon | CB 2020 ZCTA5 1:500k + 2025 gazetteer | `aland`, `intpt_lat/lon` |
| `regions` | polygon | curated regions as unions of counties (see [Regions layer](#regions-layer-us-canada-and-india-packs)) | `kind`, `members`, `aliases`, `area_km2` |

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
  found in 2025). `population` is the newest SUB-EST estimate, which covers incorporated places
  (and Urban Honolulu CDP) only: other CDPs, inactive places and the Island Areas are null. The
  Las Vegas Strip is in Paradise CDP, not Las Vegas city: names people use and Census names differ.
- **ZCTAs** are the Census Bureau's areal approximation of USPS ZIP Codes. USPS publishes ZIP Codes
  as delivery routes, not areas; most addresses' ZIP matches their ZCTA but not all, PO-box-only
  ZIPs have no ZCTA, and unpopulated land is in none. ZCTAs are defined once a decade, so the
  2020 file is current. Polygons cost about 52 MB of the pack (26 MB of the archive); gazetteer
  points would be 2 MB, but the nearest internal point names the containing ZCTA only ~70% of
  the time near populated places, so the pack ships polygons (`uscensus.zcta_points` is the
  alternative).
- **Shoreline.** CB shapes are clipped to the shoreline: points in bays and coastal water fall in
  no county, place or ZCTA, and gazetteer internal points (computed from full TIGER/Line) can fall
  outside the clipped shape (San Francisco's is on the Farallon Islands).
- **Delineation.** OMB list 1 is an .xlsx; it is read with the standard library (zip + XML).

## Canada pack (`can`)

```
uv run python -m packbuild.ca --version 2026.11 --via service   # writes .cache/packbuild/out/can-2026.11/
```

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `provinces` | polygon | StatCan 2021 cartographic boundary file, provinces/territories (`lpr_000b21a_e`) | StatCan Open Licence |
| `cd` | polygon | ... census divisions (`lcd_000b21a_e`): counties, regional municipalities (Halton, Peel) | StatCan Open Licence |
| `csd` | polygon | ... census subdivisions (`lcsd000b21a_e`): municipalities (Milton, Toronto), reserves, unorganised areas | StatCan Open Licence |
| `cma` | polygon | ... census metropolitan areas and agglomerations (`lcma000b21a_e`) | StatCan Open Licence |
| `fsa` | polygon | 2021 Census forward sortation area boundary file (`lfsa000b21a_e`) | StatCan Open Licence, with Canada Post's notice |
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
cached under `.cache/packbuild/<layer>/` with a `<layer>.json` sidecar. The service's gateway gives
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
uv run python -m packbuild.india --version 2026.11     # writes .cache/packbuild/out/ind-2026.11/
uv run python -m packbuild.india --version 2026.11 \
    --pincode-boundaries All_India_pincode_Boundary-19312.geojson --pincode-directory pincode.csv
```

| Layer | Kind | Source | Licence |
|---|---|---|---|
| `pincodes` | polygon | All India Pincode Boundary (Department of Posts, 2025), district and state joined from the directory | GODL-India |
| `post_offices` | point | All India Pincode Directory (Department of Posts): offices whose coordinates lie in or within 2 km of their own PIN area | GODL-India |
| `regions` | polygon | curated regions as unions of PIN areas grouped by district (see [Regions layer](#regions-layer-us-canada-and-india-packs)) | CC BY 4.0 + GODL-India |

Registry: `indiapost-pincode-boundary`, `indiapost-pincode-directory`. Ids: `pin:560001`;
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
- **Disputed areas.** PIN areas are delivery zones as published by the Department of Posts (a
  Government of India body), not administrative boundaries; the pack carries them unchanged.
  Whether any extend into areas whose status is disputed has not been checked yet (do it on the
  first real build).

**Not here:**

- *State and district polygons.* No source passed the licence gate. The Survey of India's
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
- *Census 2011 towns.* The Town Directory has no coordinates; GeoNames in the world pack covers
  towns.

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
  Post directory spells them) and its members are the PIN areas filed under them. A PIN area can
  cross a district line, so those outlines are the postal approximation of the districts.
- **Build-time checks.** A member missing from the pack's layers, a region with no members, or
  (India) members that are not exactly the PIN areas of the listed districts fail the build with
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

## Releasing data

Packs are published as GitHub release assets of `amolvenkataraman/placewise-data` (no data in its
git history; see its README). placewise's default index URL is that repository's
`releases/latest/download/index.json`, so **every release must list every pack**: an unchanged
pack is released again under the new tag.

```
# 1. build the packs (each writes .cache/packbuild/out/<name>-<version>/)
uv run python -m packbuild.world --version 2026.11
uv run python -m packbuild.us --version 2026.11

# 2. prepare: verify, archive, index (nothing is uploaded; prints the gh command it would run)
uv run python -m packbuild.release \
    --packs .cache/packbuild/out/world-2026.11 .cache/packbuild/out/usa-2026.11 \
    --out .cache/packbuild/release/2026.11

# 3. test the release directory as placewise would use it
uv run placewise --data-dir /tmp/pw-test \
    --index-url file://$PWD/.cache/packbuild/release/2026.11/index.json data install world
uv run placewise --data-dir /tmp/pw-test \
    --index-url file://$PWD/.cache/packbuild/release/2026.11/index.json data verify

# 4. publish (needs both the flag and the environment switch; uses gh's login)
PLACEWISE_ALLOW_PUBLISH=1 uv run python -m packbuild.release \
    --packs .cache/packbuild/out/world-2026.11 .cache/packbuild/out/usa-2026.11 \
    --out .cache/packbuild/release/2026.11 --publish [--tag 2026.11]
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
