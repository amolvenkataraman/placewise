# Parks and protected areas

`Result.within` lists every park whose outline contains the point, most significant first (lower
tier first, then the smaller park); `Result.near` lists, after the notable cities, up to 3 parks the
point is not inside, nearest first. Engine: `placewise.engine._nearby.parks`; constants:
`placewise.constants.parks`; distances: `NearSettings.park_tier1..3`. Inside a tier 1 or 2 park
(not a national forest or grassland) the default label names it: "Yosemite Valley, Yosemite
National Park" (docs/naming.md, `label.parks`); label templates get `{within}`.

| Tier | Meaning | Near | US | Canada | Europe (eur-parks) | Elsewhere (points) |
|---|---|---|---|---|---|---|
| 1 | national | 25 km | NPS parks, preserves, seashores, lakeshores, NRAs, monuments >= 10 km² | CPCAD national parks, park reserves, Rouge NUP, NMCAs | national parks (their core areas; not buffer, peripheral or adhesion zones) | Wikidata national parks, tiger reserves |
| 2 | state / provincial, national forests | 10 km | USFS administrative forests; PAD-US SP, SREC, SW, NCA, NSBV, non-NPS NM/NRA; refuges (Proclamation) | provincial and territorial parks, Quebec national parks, Gatineau Park | nature, natural, regional and landscape parks, protected landscape areas, biosphere reserves; IUCN II sites >= 100 km² | wildlife refuges and sanctuaries |
| 3 | regional / conservation | 1 km | small NPS sites; PAD-US SCA, SHCA, SRMA, SOTH, RMA, HCA, REC, SDA, LCA, LRMA | conservation and ecological reserves, NWAs, MBSs, conservation areas | nature reserves, strict reserves, protected landscapes, zones inside national parks; >= 1 km² | other Indian protected areas |
| 4 | local | inside only | PAD-US LP, LREC, LHCA; NPS rivers, trails, parkways | municipal parks and natural areas | - | - |

Crosswalks: `packbuild/sources/parks/tiers.py`; anything unlisted is dropped (easements, private
and NGO land, habitat designations, OECMs, military and tribal land, PAD-US land closed to the public).
Europe's 739 national designation types are ranked by rules on their English names (`eea_tier`),
not a table: only category A (nature and landscape protection) is kept, apart from national parks;
international designations reported again as national (Natura 2000, Ramsar, Emerald), buffer and
development zones, Germany's and Austria's landscape protection areas (a third of Germany),
habitats, single objects and sectoral (forest, hunting, water) designations are dropped.
Nature parks, biosphere reserves and protected landscapes take in whole towns, so like national
forests they are never the label (`LABEL_SKIP_DESIGNATIONS`).

Names that only say what kind of land a parcel is ("Unknown Park", "Open Space", "Conservation
Easement", "Natural Area": `placewise.constants.parks.GENERIC_NAMES`) are never a park's name. The
build takes PAD-US's local name (`Loc_Nm`) instead when that is a real name, else leaves the parcel
out (`tiers.place_name`; the managing agency is only a code such as `CITY`, so it can't stand in);
CPCAD has none today but gets the same rule. Packs built before this still carry such rows: the
engine never puts them in `within` or `near`, and search never returns them.

## Packs

| Pack | Layers | Sources |
|---|---|---|
| `usa-parks` | `parks_national`, `parks_state`, `parks_regional` (polygons) | NPS boundaries, USFS administrative forests, PAD-US 4.1 (all public domain) |
| `usa-parks-local` | `parks_local` (polygons): city and county parks, optional beside usa-parks | PAD-US 4.1 (public domain) |
| `can-parks` | the same four | CPCAD December 2025 (OGL-Canada 2.0) |
| `eur-parks` | `parks_national`, `parks_state`, `parks_regional`: 37 European countries, optional | EEA Nationally designated areas, July 2026 (CC BY 4.0); English names from Wikidata (CC0) |
| `world-parks` | `park_points` (points) | Wikidata (CC0) |

Separate packs rather than layers in `usa`/`can`/`world`: those packs are built by other builders,
the outline packs are large (can-parks 33 MB unpacked), and parks install and update on their own.
The US's 120k local parks were most of usa-parks, so they are a pack of their own, `usa-parks-local`
(pack.json `kind` parks, `covers` US, `requires` usa-parks): with it a point in Central Park is
`within` it, without it the national, state and regional answers are the same and local parks are
neither within nor found by search. eur-parks (pack.json `kind` parks, `covers` the countries it
has sites in) is optional in the same way: without it Europe's national parks are world-parks
points. With it, a world-parks point named like an outline park found for the same point is that
park and is not listed again. world-parks is 0.6 MB, but keeping it apart lets the world pack stay
unchanged. The default Geocoder opens installed park packs.

Columns: `id` (unique per row), `park` (the Place id, shared by a park's parcels or zones), `name`,
`tier`, `designation`, `area_km2` (the whole park's), `aliases` (pipe-separated: short name, official
form), `code` (NPS unit code, USFS forest code). Points add `radius_km`, `wikidata`, `sitelinks`.

Ids: `nps:YOSE` (a second unit under one code adds its designation: `nps:DENA:national-preserve`),
`usfs:0505`, `cpcad:<PARENT_ID>` (Banff `cpcad:710300000`), `eea:<natDAId>` (the EEA site code,
also the site's WDPA id: Plitvice Lakes `eea:1054`), `wikidata:Q192764`, and for PAD-US,
which has no persistent ids, `pad-us:<state>:<des_tp>:<name slug>:<geohash5>`: parcels grouped by
state, designation and name, split into clusters whose boxes come within 1 km, the geohash that of
the cluster's largest parcel's centre.

## Sources and how they are read

None of the outline sources ships a format placewise reads without GDAL (all are File
Geodatabases), so the build reads each agency's own ArcGIS service of the same edition
(`packbuild/sources/parks/_rest.py`), generalised by the service to 10 m: NPS and PAD-US in Web
Mercator, CPCAD in EPSG:3978 (unprojected with `packbuild/projection.py`; checked against the
service's own EPSG:4326 output to 1e-9 degrees). The USFS shapefile is simplified locally.
Downloads: about 390 MB (PAD-US Fee 195 MB, CPCAD 96 MB, USFS 45 MB, refuges 45 MB, NPS 8 MB).

## Europe (eur-parks)

The EEA's Nationally designated areas (formerly CDDA; July 2026, version 24) are what 37 European
countries report as their own designations, the official European source behind the WDPA, under
CC BY 4.0. The continental GeoPackage (1.7 GB) is read with sqlite3 (`packbuild/gpkg.py`: the
GeoPackage header and WKB) and unprojected from ETRS89-LAEA (EPSG:3035, `packbuild/projection.py`,
checked against IOGP Guidance Note 7-2's worked example). A site is one row (its multipolygon,
simplified to 10 m); sites reported only as a point are skipped.

- **Names.** As reported, in the national language ("Plitvička jezera", "Nationalpark", "P N Delle
  Cinque Terre"), with Sweden's id prefixes and Latvia's zone codes removed and ALL CAPS in title
  case; English where Wikidata has an English label for an item whose WDPA id (P809) is the site's
  natDAId ("Plitvice Lakes National Park", "Swiss National Park", "Cinque Terre National Park"),
  the oldest item when several share one id. The national names are then aliases. Most national
  parks have an English name this way; most reserves keep their national one.
- **One park, several sites.** Some parks are reported as zones (Hohe Tauern: a core and an outer
  zone in each of three states; Latvia's national parks: dozens of zones). Tier 1 and 2 sites of one
  country and designation type whose boxes come within 1 km, one of whose (folded) names holds the
  other's as whole words, are one park, with the id and name of the site that has an English name,
  else of the one with the shortest name.
- **Coverage.** No United Kingdom (out of the EEA's data since 2021) and no Türkiye; Estonia and
  Ireland only in part (the EEA may not publish all their sites). Overseas entities are in another
  file, not read.
- **Size** (2026.11.1): 14,124 sites in 13,473 parks (tier 1: 510 sites in 357 parks; tier 2:
  1,486; tier 3: 12,128) from 142,053; 39.3 MB installed (parks_regional 25, parks_state 7.3,
  parks_national 4.0, name index 1.6), a 19.8 MB download. The build reads the 1.7 GB GeoPackage
  in about 85 s and 1.2 GB of memory.
- **Natura 2000** is not used: it repeats NatDA's protected land under habitat-directive names
  (often in the national language), and the places people name (national parks, nature parks,
  reserves) are national designations already.

## Points without outlines (India and the rest of the world)

Wikidata items with a point and an English label; radius = that of a circle of the item's area
(P2046), capped at 30 km, or 0. They are never `within`: inside the circle they are `near` at 0 km
("in the area of"), beyond it near up to their tier's distance. India has no openly licensed park
outlines (`sources/parks.json` gaps). Parks carry no country: the boundary layers and the worldview
decide it, so no park asserts sovereignty over a disputed area (Wikidata places Deosai and Khunjerab
National Parks, in Gilgit-Baltistan, in Pakistan; that is only used to leave US and Canadian items out).

## Known gaps

- United Kingdom park outlines (the EEA dropped the UK; the UK agencies' OGL data isn't read yet):
  Lake District, Peak District and the others are world-parks points.

- Queen Victoria Park (Niagara Parks Commission) is not in CPCAD; CPCAD has almost no city parks.
- PAD-US Designation layer (wilderness areas) is not read.
