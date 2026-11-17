# Data attribution

**Disclaimer.** placewise and its data packs are provided "as is" and "where is", without warranty
of any kind and with no legal liability for their use. The data may be wrong, incomplete or out of
date, and is not an official determination of any place's name, boundaries or status. See
[DISCLAIMER.md](DISCLAIMER.md).

Generated from the source registry (`src/placewise/sources/`) by `placewise attribution --all`; do
not edit by hand. It lists every dataset placewise data packs are built from, with its licence and
the credit line to show. An app that ships or displays placewise data can link to this file, and
should still read each licence for its own obligations.

| Source | Licence | Used in |
|---|---|---|
| [OurAirports](https://ourairports.com/data/) | LicenseRef-public-domain | world/airports |
| [Natural Earth 1:10m Cultural Vectors](https://www.naturalearthdata.com) | LicenseRef-public-domain | world/countries, world/admin1, world/worldviews, world/country_facts, world/timezones |
| [US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | LicenseRef-public-domain | usa/states, usa/counties, usa/places, usa/cbsa, usa/csa, usa/zcta, usa/regions, usa/timezones |
| [Statistics Canada, 2021 Census Boundary Files (cartographic)](https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21) | LicenseRef-StatCan-Open-Licence | can/provinces, can/cd, can/csd, can/cma, can/regions, can/timezones |
| [GeoNames](https://www.geonames.org) | CC-BY-4.0 | world/country_facts, world/cities, package: constants/countries/<country>/cities.py (generated), usa/zcta |
| [Unicode CLDR (Common Locale Data Repository), cldr-json 49.0.0](https://cldr.unicode.org) | Unicode-3.0 | world/country_facts, package: constants/countries/currency_codes.py (generated) |
| [Wikidata](https://www.wikidata.org) | CC0-1.0 | world/country_facts, world-water/lakes |
| [Statistics Canada, 2021 Census of Population, population and dwelling counts](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201) | LicenseRef-StatCan-Open-Licence | can/provinces, can/cd, can/csd, can/cma, can/fsa |
| [Canadian Geographical Names Database (CGNDB), Natural Resources Canada](https://open.canada.ca/data/en/dataset/e27c6eba-3c5d-4051-9db2-082dc6411c2c) | OGL-Canada-2.0 | can/populated_places |
| [Statistics Canada, 2021 Census Forward Sortation Area Boundary File (cartographic)](https://www150.statcan.gc.ca/n1/en/catalogue/92-179-X) | LicenseRef-StatCan-Open-Licence | can/fsa |
| [All India Pincode Boundary (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json) | LicenseRef-GODL-India | ind/pincodes, ind/regions |
| [All India Pincode Directory (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-directory) | LicenseRef-GODL-India | ind/pincodes, ind/post_offices, ind/regions |
| [placewise curated datasets: regions (datasets/regions)](https://github.com/amolvenkataraman/placewise-data/tree/main/datasets) | CC-BY-4.0 | usa/regions, can/regions, ind/regions |
| [placewise curated datasets: time zones (datasets/timezones)](https://github.com/amolvenkataraman/placewise-data/tree/main/datasets) | CC-BY-4.0 | world/timezones, usa/timezones, can/timezones |
| [Natural Earth 1:10m Physical Vectors](https://www.naturalearthdata.com) | LicenseRef-public-domain | world-water/marine, world-water/lakes, world-water/rivers |
| [HydroLAKES v1.0](https://www.hydrosheds.org/products/hydrolakes) | CC-BY-4.0 | world-water/lakes |

## Coverage

| Purpose | Region | Sources |
|---|---|---|
| airports | world | OurAirports |
| boundaries | world | Natural Earth 1:10m Cultural Vectors |
| boundaries | can | Statistics Canada, 2021 Census Boundary Files (cartographic) |
| boundaries | ind | none: No openly licensed, redistributable state or district boundaries found yet (Survey of India data is not under an open licence; NWDP's terms are unclear; geoBoundaries is CC BY 2.5 IN or ODbL). Natural Earth admin1 covers states in the world pack. See packbuild/README.md, India pack. |
| boundaries | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| countries | world | GeoNames, Unicode CLDR (Common Locale Data Repository), cldr-json 49.0.0, Wikidata, Natural Earth 1:10m Cultural Vectors |
| places | world | GeoNames |
| places | can | Statistics Canada, 2021 Census of Population, population and dwelling counts, Canadian Geographical Names Database (CGNDB), Natural Resources Canada |
| places | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| postal | can | Statistics Canada, 2021 Census Forward Sortation Area Boundary File (cartographic), Statistics Canada, 2021 Census of Population, population and dwelling counts |
| postal | ind | All India Pincode Boundary (Department of Posts, Open Government Data Platform India), All India Pincode Directory (Department of Posts, Open Government Data Platform India) |
| postal | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations, GeoNames |
| regions | can | Statistics Canada, 2021 Census Boundary Files (cartographic), Statistics Canada, 2021 Census of Population, population and dwelling counts, placewise curated datasets: regions (datasets/regions) |
| regions | ind | All India Pincode Boundary (Department of Posts, Open Government Data Platform India), All India Pincode Directory (Department of Posts, Open Government Data Platform India), placewise curated datasets: regions (datasets/regions) |
| regions | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations, placewise curated datasets: regions (datasets/regions) |
| timezones | world | placewise curated datasets: time zones (datasets/timezones), Natural Earth 1:10m Cultural Vectors |
| timezones | can | placewise curated datasets: time zones (datasets/timezones), Statistics Canada, 2021 Census Boundary Files (cartographic) |
| timezones | usa | placewise curated datasets: time zones (datasets/timezones), US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| water | world | Natural Earth 1:10m Physical Vectors, HydroLAKES v1.0, Wikidata |

## OurAirports

- Credit: OurAirports (ourairports.com), public domain
- Licence: LicenseRef-public-domain
- Website: https://ourairports.com/data/

Released into the public domain by the maintainers. The world pack keeps large and medium airports plus small ones with scheduled service.

## Natural Earth 1:10m Cultural Vectors

- Credit: Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.
- Licence: LicenseRef-public-domain
- Website: https://www.naturalearthdata.com

Public domain (naturalearthdata.com/about/terms-of-use). Borders are de facto; per-country ADM0_A3_XX and FCLASS_XX columns describe other worldviews and are kept for the worldview setting; the disputed-areas file (99 polygons with every view's ADM0_A3_XX) is the world pack's worldviews layer. Text fields are NUL-padded.

country_facts uses each country's label point (LABEL_X, LABEL_Y) where GeoNames has no capital.

## US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations

- Credit: U.S. Census Bureau (census.gov), public domain
- Licence: LicenseRef-public-domain
- Website: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html

Works of the US federal government are not subject to copyright (17 U.S.C. 105). Boundaries are the 2025 cartographic boundary files at 1:500,000 (generalised from TIGER/Line and clipped to the shoreline, so points in bays and coastal water fall in no county or place); ZIP Code Tabulation Areas exist only in the 2020 vintage, since ZCTAs are defined once per decennial census. ZCTAs approximate USPS ZIP Code delivery areas, which USPS does not publish as areas. Place populations are the Vintage 2025 Population Estimates (SUB-EST2025, July 2025) for incorporated places (and Urban Honolulu CDP, Hawaii having no incorporated places), and the American Community Survey 2020-2024 5-year estimates (table B01003, total population, from the table-based summary file, which needs no API key) for census-designated places and any place SUB-EST lacks; ZCTA populations are ACS too. CBSA and CSA membership is the July 2023 delineation (OMB Bulletin 23-01): list 1 for counties, list 2 for principal cities. Each ZCTA's postal city name is the city ZIP Code Business Patterns 2023 (County Business Patterns program) gives its ZIP Code, matched to a census place by name within the state, preferring places the 2020 ZCTA-to-place relationship file says overlap the ZCTA; ZIP Codes Business Patterns lacks are named from the other US postal source in postal.json. The files are NAD83 (EPSG:4269), used as WGS84: the two differ by 1-2 m in the US, within the generalisation of these files.

The American Indian/Alaska Native/Native Hawaiian Areas cartographic boundary file (2025, 1:500,000) draws the Navajo Nation (which observes daylight saving time inside Arizona) and the Annette Island Reserve (America/Metlakatla).

## Statistics Canada, 2021 Census Boundary Files (cartographic)

- Credit: Adapted from Statistics Canada, 2021 Census Boundary Files (cartographic), reference date January 1, 2021. This does not constitute an endorsement by Statistics Canada of this product.
- Licence: LicenseRef-StatCan-Open-Licence
- Website: https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21

Statistics Canada Open Licence (statcan.gc.ca/en/terms-conditions/open-licence); the credit is the licence's required notice for value-added products (the pack reprojects and simplifies the boundaries). Catalogue 92-160-X, reference guide 92-160-G. Cartographic files: clipped to the shoreline (coastal water belongs to no area) but not generalised, with a vertex every few metres; the build simplifies them (Douglas-Peucker, 10 m, per feature). Published only in Statistics Canada Lambert (EPSG:3347, NAD83); the build unprojects to longitude/latitude and uses NAD83 as WGS84 (1-2 m apart in Canada). The zips (Shapefile) sit on www12.statcan.gc.ca, which answers scripted downloads with a browser check (HTTP 403); 'service' is StatCan's own ArcGIS REST service of the same 2021 cartographic files (layers lpr_000b21s_e etc.), which the build can read instead (--via service). Names are StatCan's official forms, some bilingual ('Greater Sudbury / Grand Sudbury'). The Open Government Portal lists the same files under the Open Government Licence - Canada.

## GeoNames

- Credit: GeoNames (geonames.org), CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://www.geonames.org

The world pack's country_facts layer takes capital, area, population, top-level domain, calling code, postal code format, languages and neighbours from countryInfo.txt, each country's IANA time zones from timeZones.txt, and the capital's coordinates from cities1000 (the PPLC city). countryInfo gives no reference year for its population and area figures, so the layer carries none.

Places with population 1000+. Each city carries an IANA time zone, used for time zones until a boundary pack exists.

GeoNames postal codes for the United States (export/zip/US.zip: 41,490 ZIP Codes with the USPS default city name, state, county and a centroid), under CC BY 4.0 per its readme. The US pack takes a ZCTA's postal city from it only where ZIP Code Business Patterns has no row for the ZIP Code (about 2,700 of 33,791 ZCTAs, mostly rural residential ones); the readme does not name the upstream source of the US file.

## Unicode CLDR (Common Locale Data Repository), cldr-json 49.0.0

- Credit: Unicode Common Locale Data Repository (CLDR), Copyright © 2015-2024 Unicode, Inc., Unicode License v3
- Licence: Unicode-3.0
- Website: https://cldr.unicode.org

The cldr-json packages (github.com/unicode-org/cldr-json), pinned to release 49.0.0. Currency per territory (the first current legal tender in currencyData, an ISO 4217 code; also the package's offline currency_codes table) with its English name and symbols; measurement system (CLDR 'UK' is read as imperial-mixed) and first day of the week per territory, falling back to CLDR's world default (001) as CLDR does; and the short date pattern of each territory's likely locale (likelySubtags 'und-XX'), read from '<dates><locale>/ca-gregorian.json'. cldr-json locale files are resolved, so a regional locale already carries what it inherits. CLDR has no driving side.

## Wikidata

- Credit: Wikidata (wikidata.org), CC0
- Licence: CC0-1.0
- Website: https://www.wikidata.org

Driving side (property P1622, values Q11920728 left and Q14565199 right) of every item with an ISO 3166-1 alpha-2 code (P297), leaving out deprecated statements and ones with an end time (P582). A code whose current statements disagree gets no driving side. The query result is cached on the first build; rebuilding with --refresh asks again.

English names of lakes (Q23397), reservoirs (Q131681), lagoons (Q187223), salt lakes (Q188025), marine lakes (Q1898470), artificial lakes (Q3215290) and crater lakes (Q204324) that have coordinates and an English Wikipedia article, two queries (about 14,000 and 4,000 items, November 2026). An item names a HydroLAKES outline its point falls in when neither Natural Earth nor another item already names it (Dal Lake, Wular Lake, Loktak Lake).

## Statistics Canada, 2021 Census of Population, population and dwelling counts

- Credit: Adapted from Statistics Canada, Census of Population 2021, Population and dwelling counts (tables 98-10-0002-01, 98-10-0005-01 and 98-10-0019-01), reference date May 11, 2021. This does not constitute an endorsement by Statistics Canada of this product.
- Licence: LicenseRef-StatCan-Open-Licence
- Website: https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201

Full-table CSV downloads. 98-10-0002-01 covers Canada, provinces and territories, census divisions and census subdivisions; 98-10-0005-01 CMAs and CAs (whole and by provincial part); 98-10-0019-01 forward sortation areas. Joined to the boundaries on DGUID. 63 CSDs (incompletely enumerated Indian reserves and settlements) have no count (symbol '..'); they are stored as null, not zero.

## Canadian Geographical Names Database (CGNDB), Natural Resources Canada

- Credit: Contains information licensed under the Open Government Licence – Canada (Canadian Geographical Names Database, Natural Resources Canada).
- Licence: OGL-Canada-2.0
- Website: https://open.canada.ca/data/en/dataset/e27c6eba-3c5d-4051-9db2-082dc6411c2c

Official geographical names approved by the Geographical Names Board of Canada and its provincial and territorial members, refreshed weekly (the national English-format CSV; names keep the language they were decided in, English or French, and are not translated). The Canada pack keeps generic category 'Populated Place' (hamlets, communities, towns, urban communities, neighbourhoods, Montreal's boroughs: about 26,000 points) without railway points, post offices, stations and former or vacated places, with the 'Relevance at Scale' field as a prominence. Coordinates are NAD83, used as WGS84. Points only, no boundaries or populations.

## Statistics Canada, 2021 Census Forward Sortation Area Boundary File (cartographic)

- Credit: Adapted from Statistics Canada, 2021 Census Forward Sortation Area Boundary File, reference date January 1, 2021. This does not constitute an endorsement by Statistics Canada of this product. This data includes information copied with permission from Canada Post Corporation. Postal code is an official mark of Canada Post.
- Licence: LicenseRef-StatCan-Open-Licence
- Website: https://www150.statcan.gc.ca/n1/en/catalogue/92-179-X

Catalogue 92-179-X, reference guide 92-179-G, whose use is governed by the Statistics Canada Open Licence; the guide carries the Canada Post notice repeated in the credit. 1,643 census FSAs (first three characters of the postal code) built from the postal codes census respondents reported: each dissemination area is assigned one FSA, so boundaries follow dissemination areas and can differ from Canada Post's delivery FSAs. Full six-character postal codes and their locations are Canada Post data, not open data, and are not used anywhere in placewise. Same projection, download and browser-check notes as statcan-boundaries-2021; the service is layer lfsa000b21s_e of the same map service.

## All India Pincode Boundary (Department of Posts, Open Government Data Platform India)

- Credit: Department of Posts, Ministry of Communications, Government of India. All India Pincode Boundary Geo JSON, sourced from the Open Government Data (OGD) Platform India (data.gov.in), under the Government Open Data Licence - India (GODL), https://www.data.gov.in/Godl
- Licence: LicenseRef-GODL-India
- Website: https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json

Geofenced delivery post office PIN code areas (19,312 polygons) published by the Department of Posts in 2025, with the 'Know Your PIN Code' portal, under GODL-India, which permits use, adaptation and redistribution, commercial or not, with attribution to the provider, source and licence. The official catalogue page (data.gov.in) and its AIKosh copies (https://aikosh.indiaai.gov.in/home/datasets/details/all_india_pincode_boundary_geo_json.html, https://aikosh.indiaai.gov.in/home/datasets/details/delivery_post_office_pincode_boundary.html) offer no file that can be fetched automatically: data.gov.in refused or blocked automated requests from the build machine in November 2026 and was reported returning 404 for this resource in May 2026, and AIKosh downloads go through a click-through. The build therefore fetches boundary_mirror, a copy of the official file All_India_pincode_Boundary-19312.geojson (90,323,809 bytes, git blob 6a73f2dfc85b9c7657b24c6523e8ca882cb4a8c7, byte-identical in three unrelated GitHub repositories), pinned to a commit, or takes a manually downloaded official copy (--pincode-boundaries). GeoJSON in WGS84 longitude/latitude (CRS84); properties Pincode, Office_Name, Division, Region, Circle, text padded with trailing spaces. It carries no district or state: the build joins those from the All India Pincode Directory. Boundaries are carried as published by the Department of Posts, a Government of India body, so any official-versus-de-facto question follows India's official view; the areas are delivery zones, not administrative units, and do not nest inside states or districts.

India's curated regions are drawn as unions of PIN code areas grouped by district, since no district polygons are openly licensed.

## All India Pincode Directory (Department of Posts, Open Government Data Platform India)

- Credit: Department of Posts, Ministry of Communications, Government of India. All India Pincode Directory, sourced from the Open Government Data (OGD) Platform India (data.gov.in), under the Government Open Data Licence - India (GODL), https://www.data.gov.in/Godl
- Licence: LicenseRef-GODL-India
- Website: https://www.data.gov.in/catalog/all-india-pincode-directory

Every post office with its PIN code, office type (HO, SO, BO), delivery status, division, region, circle, district, state and, for most offices, a latitude and longitude, published under GODL-India (use, adaptation and redistribution allowed with attribution). The official file is the CSV download of data.gov.in resource 'All India Pincode Directory till last month' (API resource 5c2f62fe-5afa-4119-a499-fec9d604d5bd, which needs a free data.gov.in API key); data.gov.in refused or blocked automated requests from the build machine in November 2026. The build therefore fetches directory_mirror, a copy of that CSV taken from data.gov.in in May 2024 and pinned to a commit, or takes a manually downloaded current CSV (--pincode-directory). District and state names are upper case as published. Coordinates are WGS84; placeholder values (NA, 1/1, blanks) and points outside India's extent are dropped, not repaired. Districts and states are the Department of Posts' own assignment of each office.

The directory's district column decides which PIN areas make up a district.

## placewise curated datasets: regions (datasets/regions)

- Credit: placewise curated datasets, CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://github.com/amolvenkataraman/placewise-data/tree/main/datasets

Curated by the placewise project and licensed CC BY 4.0 (datasets/LICENSE.md in the placewise-data repository): each region's name, aliases, kind, cited definition and member units. The outlines in the packs are unions of the member units' boundaries, so they are also credited to the boundary source.

## placewise curated datasets: time zones (datasets/timezones)

- Credit: placewise curated datasets, CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://github.com/amolvenkataraman/placewise-data/tree/main/datasets

Curated by the placewise project and licensed CC BY 4.0 (datasets/LICENSE.md in the placewise-data repository): the IANA zone of each country, admin-1 unit, county or census subdivision, with the tz database (public domain), 49 CFR Part 71 (public domain) and the provincial acts cited per entry, and a few hand-drawn areas (Eucla, the western Aleutians, research stations). The outlines in the packs are the units' own boundaries, so they are also credited to the boundary source. Zone names are checked against the tz database at build time.

## Natural Earth 1:10m Physical Vectors

- Credit: Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.
- Licence: LicenseRef-public-domain
- Website: https://www.naturalearthdata.com

Public domain (naturalearthdata.com/about/terms-of-use). Version 5.1 marine polygons (geography_marine_polys: 306 seas, gulfs, bays, straits and ocean halves covering the whole ocean, 271 with Wikidata ids), lakes with the North America and Europe supplements, and river centerlines with the same supplements. Marine names are name_en (from Wikidata labels) except oceans and rivers, which keep name ('North Atlantic Ocean' where name_en says 'Atlantic Ocean'); lakes keep name, which holds the generic ('Lake Ontario' where name_en says 'Ontario'); unnamed features and lake centerlines are left out. namealt holds alternatives such as Persian Gulf / Arabian Gulf and Sea of Japan / East Sea (aliases; per-worldview water names are not applied yet). These replace the Marine Regions IHO Sea Areas, which are CC BY-NC-SA 4.0 (non-commercial: rejected).

## HydroLAKES v1.0

- Credit: HydroLAKES: Messager, M.L., Lehner, B., Grill, G., Nedeva, I., Schmitt, O. (2016): Estimating the volume and age of water stored in global lakes using a geo-statistical approach. Nature Communications 7: 13603. doi:10.1038/ncomms13603. Data at www.hydrosheds.org, CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://www.hydrosheds.org/products/hydrolakes

CC BY 4.0 (HydroLAKES Technical Documentation v1.0, section 4.1), which also asks users "to refrain from redistributing the data in whole in its original format on other websites without the explicit written permission from the authors": the pack carries a filtered, simplified derivative in placewise's own format (lakes of 10 km² or more, about 1.2% of the 1.43 million lakes, outlines simplified to 30 m), not the original files. The build reads only the start of the 820 MB archive by HTTP range requests (its records run largest first), about 220 MB in all. Names are joined from Natural Earth and Wikidata (packbuild.sources.water.names); HydroLAKES' Country field is the country of the outflow (Lake Ontario: United States), so it is not used: a lake's country comes from the world pack's polygons and the worldview.
