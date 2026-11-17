# Data attribution

Generated from the source registry (`src/placewise/sources/`) by `placewise attribution`; do not
edit by hand. It lists every dataset placewise data packs are built from, with its licence and
the credit line to show. An app that ships or displays placewise data can link to this file, and
should still read each licence for its own obligations.

| Source | Licence | Used in |
|---|---|---|
| [OurAirports](https://ourairports.com/data/) | LicenseRef-public-domain | world/airports |
| [Natural Earth 1:10m Cultural Vectors](https://www.naturalearthdata.com) | LicenseRef-public-domain | world/countries, world/admin1 |
| [US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | LicenseRef-public-domain | us/states, us/counties, us/places, us/cbsa, us/csa, us/zcta |
| [GeoNames](https://www.geonames.org) | CC-BY-4.0 | world/cities |
| [All India Pincode Boundary (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json) | LicenseRef-GODL-India | in/pincodes |
| [All India Pincode Directory (Department of Posts, Open Government Data Platform India)](https://www.data.gov.in/catalog/all-india-pincode-directory) | LicenseRef-GODL-India | in/pincodes, in/post_offices |

## Coverage

| Purpose | Region | Sources |
|---|---|---|
| airports | world | OurAirports |
| boundaries | world | Natural Earth 1:10m Cultural Vectors |
| boundaries | in | none: No openly licensed, redistributable state or district boundaries found yet (Survey of India data is not under an open licence; NWDP's terms are unclear; geoBoundaries is CC BY 2.5 IN or ODbL). Natural Earth admin1 covers states in the world pack. See packbuild/README.md, India pack. |
| boundaries | us | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| places | world | GeoNames |
| places | us | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| postal | in | All India Pincode Boundary (Department of Posts, Open Government Data Platform India), All India Pincode Directory (Department of Posts, Open Government Data Platform India) |
| postal | us | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |
| regions | us | US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations |

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

## US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations

- Credit: U.S. Census Bureau (census.gov), public domain
- Licence: LicenseRef-public-domain
- Website: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html

Works of the US federal government are not subject to copyright (17 U.S.C. 105). Boundaries are the 2025 cartographic boundary files at 1:500,000 (generalised from TIGER/Line and clipped to the shoreline, so points in bays and coastal water fall in no county or place); ZIP Code Tabulation Areas exist only in the 2020 vintage, since ZCTAs are defined once per decennial census. ZCTAs approximate USPS ZIP Code delivery areas, which USPS does not publish as areas. Place populations are the Vintage 2025 Population Estimates (SUB-EST2025, July 2025), which cover incorporated places (and Urban Honolulu CDP, Hawaii having no incorporated places) but not other census-designated places. CBSA and CSA membership is the July 2023 delineation (OMB Bulletin 23-01). The files are NAD83 (EPSG:4269), used as WGS84: the two differ by 1-2 m in the US, within the generalisation of these files.

## GeoNames

- Credit: GeoNames (geonames.org), CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://www.geonames.org

Places with population 1000+. Each city carries an IANA time zone, used for time zones until a boundary pack exists.

## All India Pincode Boundary (Department of Posts, Open Government Data Platform India)

- Credit: Department of Posts, Ministry of Communications, Government of India. All India Pincode Boundary Geo JSON, sourced from the Open Government Data (OGD) Platform India (data.gov.in), under the Government Open Data Licence - India (GODL), https://www.data.gov.in/Godl
- Licence: LicenseRef-GODL-India
- Website: https://www.data.gov.in/catalog/all-india-pincode-boundary-geo-json

Geofenced delivery post office PIN code areas (19,312 polygons) published by the Department of Posts in 2025, with the 'Know Your PIN Code' portal, under GODL-India, which permits use, adaptation and redistribution, commercial or not, with attribution to the provider, source and licence. The official catalogue page (data.gov.in) and its AIKosh copies (https://aikosh.indiaai.gov.in/home/datasets/details/all_india_pincode_boundary_geo_json.html, https://aikosh.indiaai.gov.in/home/datasets/details/delivery_post_office_pincode_boundary.html) offer no file that can be fetched automatically: data.gov.in refused or blocked automated requests from the build machine in November 2026 and was reported returning 404 for this resource in May 2026, and AIKosh downloads go through a click-through. The build therefore fetches boundary_mirror, a copy of the official file All_India_pincode_Boundary-19312.geojson (90,323,809 bytes, git blob 6a73f2dfc85b9c7657b24c6523e8ca882cb4a8c7, byte-identical in three unrelated GitHub repositories), pinned to a commit, or takes a manually downloaded official copy (--pincode-boundaries). GeoJSON in WGS84 longitude/latitude (CRS84); properties Pincode, Office_Name, Division, Region, Circle, text padded with trailing spaces. It carries no district or state: the build joins those from the All India Pincode Directory. Boundaries are carried as published by the Department of Posts, a Government of India body, so any official-versus-de-facto question follows India's official view; the areas are delivery zones, not administrative units, and do not nest inside states or districts.

## All India Pincode Directory (Department of Posts, Open Government Data Platform India)

- Credit: Department of Posts, Ministry of Communications, Government of India. All India Pincode Directory, sourced from the Open Government Data (OGD) Platform India (data.gov.in), under the Government Open Data Licence - India (GODL), https://www.data.gov.in/Godl
- Licence: LicenseRef-GODL-India
- Website: https://www.data.gov.in/catalog/all-india-pincode-directory

Every post office with its PIN code, office type (HO, SO, BO), delivery status, division, region, circle, district, state and, for most offices, a latitude and longitude, published under GODL-India (use, adaptation and redistribution allowed with attribution). The official file is the CSV download of data.gov.in resource 'All India Pincode Directory till last month' (API resource 5c2f62fe-5afa-4119-a499-fec9d604d5bd, which needs a free data.gov.in API key); data.gov.in refused or blocked automated requests from the build machine in November 2026. The build therefore fetches directory_mirror, a copy of that CSV taken from data.gov.in in May 2024 and pinned to a commit, or takes a manually downloaded current CSV (--pincode-directory). District and state names are upper case as published. Coordinates are WGS84; placeholder values (NA, 1/1, blanks) and points outside India's extent are dropped, not repaired. Districts and states are the Department of Posts' own assignment of each office.
