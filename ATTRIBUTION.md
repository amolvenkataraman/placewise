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
| [Natural Earth 1:10m Cultural Vectors](https://www.naturalearthdata.com) | LicenseRef-public-domain | world/countries, world/admin1, world/country_facts |
| [US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | LicenseRef-public-domain | usa/states, usa/counties, usa/places, usa/cbsa, usa/csa, usa/zcta, usa/regions |
| [Statistics Canada, 2021 Census Boundary Files (cartographic)](https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21) | LicenseRef-StatCan-Open-Licence | can/provinces, can/cd, can/csd, can/cma, can/regions |
| [Sri Lanka - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-lka) | CC-BY-3.0-IGO | lka/admin1, lka/admin2, lka/admin3, lka/admin4 |
| [Nepal - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-npl) | CC-BY-3.0-IGO | npl/admin1, npl/admin2, npl/admin3 |
| [Bangladesh - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-bgd) | CC-BY-3.0-IGO | bgd/admin1, bgd/admin2, bgd/admin3 |
| [Thailand - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-tha) | CC-BY-3.0-IGO | tha/admin1, tha/admin2, tha/admin3 |
| [Viet Nam - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-vnm) | CC-BY-3.0-IGO | vnm/admin1 |
| [Mexico - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-mex) | CC-BY-3.0-IGO | mex/admin1, mex/admin2 |
| [South Africa - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-zaf) | CC-BY-3.0-IGO | zaf/admin1, zaf/admin2, zaf/admin3 |
| [Kenya - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-ken) | CC-BY-3.0-IGO | ken/admin1, ken/admin2 |
| [Egypt - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-egy) | CC-BY-3.0-IGO | egy/admin1, egy/admin2 |
| [Türkiye - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-tur) | CC-BY-3.0-IGO | tur/admin1, tur/admin2 |
| [United Arab Emirates - Subnational Administrative Boundaries (OCHA COD-AB)](https://data.humdata.org/dataset/cod-ab-are) | CC-BY-3.0-IGO | are/admin1 |
| [GeoNames](https://www.geonames.org) | CC-BY-4.0 | world/country_facts, world/cities, package: constants/countries/<country>/cities.py (generated) |
| [Unicode CLDR (Common Locale Data Repository), cldr-json 49.0.0](https://cldr.unicode.org) | Unicode-3.0 | world/country_facts, package: constants/countries/currency_codes.py (generated) |
| [Wikidata](https://www.wikidata.org) | CC0-1.0 | world/country_facts |
| [Statistics Canada, 2021 Census of Population, population and dwelling counts](https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201) | LicenseRef-StatCan-Open-Licence | can/provinces, can/cd, can/csd, can/cma, can/fsa |
| [Statistics Canada, 2021 Census Forward Sortation Area Boundary File (cartographic)](https://www150.statcan.gc.ca/n1/en/catalogue/92-179-X) | LicenseRef-StatCan-Open-Licence | can/fsa |
| [All India Pincode Boundary (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json) | LicenseRef-GODL-India | ind/pincodes, ind/regions |
| [All India Pincode Directory (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-directory) | LicenseRef-GODL-India | ind/pincodes, ind/post_offices, ind/regions |
| [placewise curated datasets: regions (datasets/regions)](https://github.com/amolvenkataraman/placewise-data/tree/main/datasets) | CC-BY-4.0 | usa/regions, can/regions, ind/regions |

## Coverage

| Purpose | Region | Sources |
|---|---|---|
| airports | world | OurAirports |
| boundaries | world | Natural Earth 1:10m Cultural Vectors |
| boundaries | are | United Arab Emirates - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | bgd | Bangladesh - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | can | Statistics Canada, 2021 Census Boundary Files (cartographic) |
| boundaries | egy | Egypt - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | ind | none: No openly licensed, redistributable state or district boundaries found yet (Survey of India data is not under an open licence; NWDP's terms are unclear; geoBoundaries is CC BY 2.5 IN or ODbL). Natural Earth admin1 covers states in the world pack. See packbuild/README.md, India pack. |
| boundaries | ken | Kenya - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | lka | Sri Lanka - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | mex | Mexico - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | npl | Nepal - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | tha | Thailand - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | tur | Türkiye - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| boundaries | vnm | Viet Nam - Subnational Administrative Boundaries (OCHA COD-AB) |
| boundaries | zaf | South Africa - Subnational Administrative Boundaries (OCHA COD-AB) |
| countries | world | GeoNames, Unicode CLDR (Common Locale Data Repository), cldr-json 49.0.0, Wikidata, Natural Earth 1:10m Cultural Vectors |
| places | world | GeoNames |
| places | can | Statistics Canada, 2021 Census of Population, population and dwelling counts |
| places | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| postal | can | Statistics Canada, 2021 Census Forward Sortation Area Boundary File (cartographic), Statistics Canada, 2021 Census of Population, population and dwelling counts |
| postal | ind | All India Pincode Boundary (Department of Posts, Open Government Data Platform India), All India Pincode Directory (Department of Posts, Open Government Data Platform India) |
| postal | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| regions | can | Statistics Canada, 2021 Census Boundary Files (cartographic), Statistics Canada, 2021 Census of Population, population and dwelling counts, placewise curated datasets: regions (datasets/regions) |
| regions | ind | All India Pincode Boundary (Department of Posts, Open Government Data Platform India), All India Pincode Directory (Department of Posts, Open Government Data Platform India), placewise curated datasets: regions (datasets/regions) |
| regions | usa | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations, placewise curated datasets: regions (datasets/regions) |

## OurAirports

- Credit: OurAirports (ourairports.com), public domain
- Licence: LicenseRef-public-domain
- Website: https://ourairports.com/data/

Released into the public domain by the maintainers. The world pack keeps large and medium airports plus small ones with scheduled service.

## Natural Earth 1:10m Cultural Vectors

- Credit: Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.
- Licence: LicenseRef-public-domain
- Website: https://www.naturalearthdata.com

Public domain (naturalearthdata.com/about/terms-of-use). Borders are de facto; per-country ADM0_A3_XX and FCLASS_XX columns describe other worldviews and are kept for the worldview setting. Text fields are NUL-padded.

country_facts uses each country's label point (LABEL_X, LABEL_Y) where GeoNames has no capital.

## US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations

- Credit: U.S. Census Bureau (census.gov), public domain
- Licence: LicenseRef-public-domain
- Website: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html

Works of the US federal government are not subject to copyright (17 U.S.C. 105). Boundaries are the 2025 cartographic boundary files at 1:500,000 (generalised from TIGER/Line and clipped to the shoreline, so points in bays and coastal water fall in no county or place); ZIP Code Tabulation Areas exist only in the 2020 vintage, since ZCTAs are defined once per decennial census. ZCTAs approximate USPS ZIP Code delivery areas, which USPS does not publish as areas. Place populations are the Vintage 2025 Population Estimates (SUB-EST2025, July 2025), which cover incorporated places (and Urban Honolulu CDP, Hawaii having no incorporated places) but not other census-designated places. CBSA and CSA membership is the July 2023 delineation (OMB Bulletin 23-01). The files are NAD83 (EPSG:4269), used as WGS84: the two differ by 1-2 m in the US, within the generalisation of these files.

## Statistics Canada, 2021 Census Boundary Files (cartographic)

- Credit: Adapted from Statistics Canada, 2021 Census Boundary Files (cartographic), reference date January 1, 2021. This does not constitute an endorsement by Statistics Canada of this product.
- Licence: LicenseRef-StatCan-Open-Licence
- Website: https://www12.statcan.gc.ca/census-recensement/2021/geo/sip-pis/boundary-limites/index2021-eng.cfm?year=21

Statistics Canada Open Licence (statcan.gc.ca/en/terms-conditions/open-licence); the credit is the licence's required notice for value-added products (the pack reprojects and simplifies the boundaries). Catalogue 92-160-X, reference guide 92-160-G. Cartographic files: clipped to the shoreline (coastal water belongs to no area) but not generalised, with a vertex every few metres; the build simplifies them (Douglas-Peucker, 10 m, per feature). Published only in Statistics Canada Lambert (EPSG:3347, NAD83); the build unprojects to longitude/latitude and uses NAD83 as WGS84 (1-2 m apart in Canada). The zips (Shapefile) sit on www12.statcan.gc.ca, which answers scripted downloads with a browser check (HTTP 403); 'service' is StatCan's own ArcGIS REST service of the same 2021 cartographic files (layers lpr_000b21s_e etc.), which the build can read instead (--via service). Names are StatCan's official forms, some bilingual ('Greater Sudbury / Grand Sudbury'). The Open Government Portal lists the same files under the Open Government Licence - Canada.

## Sri Lanka - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Sri Lanka - Subnational Administrative Boundaries: Survey Department of Sri Lanka, via OCHA (data.humdata.org/dataset/cod-ab-lka), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-lka

Common Operational Dataset, administrative boundaries, from Survey Department of Sri Lanka; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2022-08-16, reviewed 2025-10-30. Levels in the pack: ADM1 9 provinces, ADM2 25 districts, ADM3 339 divisional secretariat divisions, ADM4 14,043 Grama Niladhari divisions; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. HDX's caveat: 530 ADM4 features share an English name with differing Sinhala names (the English names are what the pack carries).

## Nepal - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Nepal - Subnational Administrative Boundaries: Survey Department of Nepal and the UN Resident Coordinator's Office in Nepal, via OCHA (data.humdata.org/dataset/cod-ab-npl), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-npl

Common Operational Dataset, administrative boundaries, from Survey Department of Nepal and the UN Resident Coordinator's Office in Nepal; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2024-03-14, reviewed 2025-10-30. Levels in the pack: ADM1 7 provinces, ADM2 77 districts, ADM3 753 local levels (metropolitan and sub-metropolitan cities, municipalities, rural municipalities) and protected areas; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. Nepal's survey draws Nepal's view of two sectors of the border with India (Kalapani, about 35 km2, and Susta, about 15 km2); there the pack's units are cut back to India's line as Natural Earth's India point-of-view edition draws it (packbuild/claims.py), so no area India claims is inside this pack.

## Bangladesh - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Bangladesh - Subnational Administrative Boundaries: Bangladesh Bureau of Statistics (BBS), via OCHA (data.humdata.org/dataset/cod-ab-bgd), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-bgd

Common Operational Dataset, administrative boundaries, from Bangladesh Bureau of Statistics (BBS); OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2023-05-21, reviewed 2025-06-01. Levels in the pack: ADM1 8 divisions, ADM2 64 districts (zila), ADM3 upazilas and metropolitan thanas; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. HDX's caveat: ADM3 holds the 495 upazilas plus metropolitan thanas and city corporations (BBS, March 2025).

## Thailand - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Thailand - Subnational Administrative Boundaries: Royal Thai Survey Department, via OCHA (data.humdata.org/dataset/cod-ab-tha), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-tha

Common Operational Dataset, administrative boundaries, from Royal Thai Survey Department; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2022-01-22, reviewed 2025-10-30. Levels in the pack: ADM1 77 provinces (changwat, with Bangkok), ADM2 928 districts (amphoe, Bangkok's khet), ADM3 7,425 subdistricts (tambon, Bangkok's khwaeng); English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. HDX's caveat: one ADM2 Thai name (TH1008) is wrong; the English names are what the pack carries.

## Viet Nam - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Viet Nam - Subnational Administrative Boundaries: General Statistics Office of Viet Nam (GSO), via OCHA (data.humdata.org/dataset/cod-ab-vnm), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-vnm

Common Operational Dataset, administrative boundaries, from General Statistics Office of Viet Nam (GSO); OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2025-09-25, reviewed 2025-09-25. Levels in the pack: ADM1 34 provinces and centrally governed cities only; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. This is the edition after the July 2025 reform (63 provinces merged into 34; districts abolished): COD-AB has no lower level yet, and the world pack's Natural Earth admin1 still has the 63 old provinces.

## Mexico - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Mexico - Subnational Administrative Boundaries: Instituto Nacional de Estadística y Geografía (INEGI), via OCHA (data.humdata.org/dataset/cod-ab-mex), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-mex

Common Operational Dataset, administrative boundaries, from Instituto Nacional de Estadística y Geografía (INEGI); OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2021-06-18, reviewed 2024-12-20. Levels in the pack: ADM1 32 states, ADM2 2,457 municipios; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m.

## South Africa - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: South Africa - Subnational Administrative Boundaries: South African Municipal Demarcation Board, via OCHA (data.humdata.org/dataset/cod-ab-zaf), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-zaf

Common Operational Dataset, administrative boundaries, from South African Municipal Demarcation Board; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2020-11-09, reviewed 2025-01-28. Levels in the pack: ADM1 9 provinces, ADM2 52 district and metropolitan municipalities, ADM3 213 local and metropolitan municipalities; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. ADM4 (wards, numbered, not named) is not used: the Demarcation Board's own terms for wards restrict commercial use.

## Kenya - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Kenya - Subnational Administrative Boundaries: Independent Electoral and Boundaries Commission (IEBC), via OCHA (data.humdata.org/dataset/cod-ab-ken), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-ken

Common Operational Dataset, administrative boundaries, from Independent Electoral and Boundaries Commission (IEBC); OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2019-10-31, reviewed 2025-01-28. Levels in the pack: ADM1 47 counties, ADM2 290 constituencies; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. HDX's caveat: not an official administrative layer of the national authorities, but agreed and endorsed for operational use by the IMWG in October 2016.

## Egypt - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Egypt - Subnational Administrative Boundaries: Central Agency for Public Mobilization and Statistics (CAPMAS), via OCHA (data.humdata.org/dataset/cod-ab-egy), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-egy

Common Operational Dataset, administrative boundaries, from Central Agency for Public Mobilization and Statistics (CAPMAS); OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2017-04-21, reviewed 2024-12-19. Levels in the pack: ADM1 27 governorates, ADM2 365 qism and markaz; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m. ADM3 (shiakha, Arabic names only) is not used. HDX's caveat: 19 ADM2 units along the Nile repeat an English name within one governorate.

## Türkiye - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: Türkiye - Subnational Administrative Boundaries: General Command of Mapping, obtained by the Regional IM Working Group - Europe, via OCHA (data.humdata.org/dataset/cod-ab-tur), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-tur

Common Operational Dataset, administrative boundaries, from General Command of Mapping, obtained by the Regional IM Working Group - Europe; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2022-01-01, reviewed 2025-01-16. Levels in the pack: ADM1 81 provinces (il), ADM2 973 districts (ilce); English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m.

## United Arab Emirates - Subnational Administrative Boundaries (OCHA COD-AB)

- Credit: United Arab Emirates - Subnational Administrative Boundaries: Federal Competitiveness and Statistics Centre, UAE Ministry of Cabinet Affairs, via OCHA (data.humdata.org/dataset/cod-ab-are), CC BY 3.0 IGO. Simplified by placewise.
- Licence: CC-BY-3.0-IGO
- Website: https://data.humdata.org/dataset/cod-ab-are

Common Operational Dataset, administrative boundaries, from Federal Competitiveness and Statistics Centre, UAE Ministry of Cabinet Affairs; OCHA publishes it on HDX under CC BY 3.0 IGO (the dataset's license_url). Reference date 2023-05-15, reviewed 2024-12-19. Levels in the pack: ADM1 7 emirates; English names (adm<n>_name), ids codab:<P-code>. Read from the shapefile zip (the edge-matched _em layers where the package has them), only the members the pack needs, by HTTP range requests; simplified with Douglas-Peucker at 10 m.

## GeoNames

- Credit: GeoNames (geonames.org), CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://www.geonames.org

The world pack's country_facts layer takes capital, area, population, top-level domain, calling code, postal code format, languages and neighbours from countryInfo.txt, each country's IANA time zones from timeZones.txt, and the capital's coordinates from cities1000 (the PPLC city). countryInfo gives no reference year for its population and area figures, so the layer carries none.

Places with population 1000+. Each city carries an IANA time zone, used for time zones until a boundary pack exists.

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

## Statistics Canada, 2021 Census of Population, population and dwelling counts

- Credit: Adapted from Statistics Canada, Census of Population 2021, Population and dwelling counts (tables 98-10-0002-01, 98-10-0005-01 and 98-10-0019-01), reference date May 11, 2021. This does not constitute an endorsement by Statistics Canada of this product.
- Licence: LicenseRef-StatCan-Open-Licence
- Website: https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810000201

Full-table CSV downloads. 98-10-0002-01 covers Canada, provinces and territories, census divisions and census subdivisions; 98-10-0005-01 CMAs and CAs (whole and by provincial part); 98-10-0019-01 forward sortation areas. Joined to the boundaries on DGUID. 63 CSDs (incompletely enumerated Indian reserves and settlements) have no count (symbol '..'); they are stored as null, not zero.

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
