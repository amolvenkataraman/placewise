# Data attribution

Generated from the source registry (`src/placewise/sources/`) by `placewise attribution`; do not
edit by hand. It lists every dataset placewise data packs are built from, with its licence and
the credit line to show. An app that ships or displays placewise data can link to this file, and
should still read each licence for its own obligations.

| Source | Licence | Used in |
|---|---|---|
| [GeoNames](https://www.geonames.org) | CC-BY-4.0 | world/cities |
| [Natural Earth 1:10m Cultural Vectors](https://www.naturalearthdata.com) | LicenseRef-public-domain | world/countries, world/admin1 |
| [OurAirports](https://ourairports.com/data/) | LicenseRef-public-domain | world/airports |
| [US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html) | LicenseRef-public-domain | us/states, us/counties, us/places, us/cbsa, us/csa, us/zcta |

## GeoNames

- Credit: GeoNames (geonames.org), CC BY 4.0
- Licence: CC-BY-4.0
- Website: https://www.geonames.org

Places with population 1000+. Each city carries an IANA time zone, used for time zones until a boundary pack exists.

## Natural Earth 1:10m Cultural Vectors

- Credit: Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.
- Licence: LicenseRef-public-domain
- Website: https://www.naturalearthdata.com

Public domain (naturalearthdata.com/about/terms-of-use). Borders are de facto; per-country ADM0_A3_XX and FCLASS_XX columns describe other worldviews and are kept for the worldview setting. Text fields are NUL-padded.

## OurAirports

- Credit: OurAirports (ourairports.com), public domain
- Licence: LicenseRef-public-domain
- Website: https://ourairports.com/data/

Released into the public domain by the maintainers. The world pack keeps large and medium airports plus small ones with scheduled service.

## US Census Bureau cartographic boundaries, gazetteer, population estimates and metro delineations

- Credit: U.S. Census Bureau (census.gov), public domain
- Licence: LicenseRef-public-domain
- Website: https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html

Works of the US federal government are not subject to copyright (17 U.S.C. 105). Boundaries are the 2025 cartographic boundary files at 1:500,000 (generalised from TIGER/Line and clipped to the shoreline, so points in bays and coastal water fall in no county or place); ZIP Code Tabulation Areas exist only in the 2020 vintage, since ZCTAs are defined once per decennial census. ZCTAs approximate USPS ZIP Code delivery areas, which USPS does not publish as areas. Place populations are the Vintage 2025 Population Estimates (SUB-EST2025, July 2025), which cover incorporated places (and Urban Honolulu CDP, Hawaii having no incorporated places) but not other census-designated places. CBSA and CSA membership is the July 2023 delineation (OMB Bulletin 23-01). The files are NAD83 (EPSG:4269), used as WGS84: the two differ by 1-2 m in the US, within the generalisation of these files.
