# Parks and protected areas

`Result.within` lists every park whose outline contains the point, most significant first (lower
tier first, then the smaller park); `Result.near` lists, after the notable cities, up to 3 parks the
point is not inside, nearest first. Engine: `placewise.engine._within`; constants:
`placewise.constants.parks`; distances: `NearSettings.park_tier1..3`. Inside a tier 1 or 2 park
(not a national forest or grassland) the default label names it: "Yosemite Valley, Yosemite
National Park" (docs/naming.md, `label.parks`); label templates get `{within}`.

| Tier | Meaning | Near | US | Canada | Elsewhere (points) |
|---|---|---|---|---|---|
| 1 | national | 25 km | NPS parks, preserves, seashores, lakeshores, NRAs, monuments >= 10 km² | CPCAD national parks, park reserves, Rouge NUP, NMCAs | Wikidata national parks, tiger reserves |
| 2 | state / provincial, national forests | 10 km | USFS administrative forests; PAD-US SP, SREC, SW, NCA, NSBV, non-NPS NM/NRA; refuges (Proclamation) | provincial and territorial parks, Quebec national parks, Gatineau Park | wildlife refuges and sanctuaries |
| 3 | regional / conservation | 1 km | small NPS sites; PAD-US SCA, SHCA, SRMA, SOTH, RMA, HCA, REC, SDA, LCA, LRMA | conservation and ecological reserves, NWAs, MBSs, conservation areas | other Indian protected areas |
| 4 | local | inside only | PAD-US LP, LREC, LHCA; NPS rivers, trails, parkways | municipal parks and natural areas | - |

Crosswalks: `packbuild/sources/parks/tiers.py`; anything unlisted is dropped (easements, private
and NGO land, habitat designations, OECMs, military and tribal land, PAD-US land closed to the public).

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
| `world-parks` | `park_points` (points) | Wikidata (CC0) |

Separate packs rather than layers in `usa`/`can`/`world`: those packs are built by other builders,
the outline packs are large (can-parks 33 MB unpacked), and parks install and update on their own.
The US's 120k local parks were most of usa-parks, so they are a pack of their own, `usa-parks-local`
(pack.json `kind` parks, `covers` US, `requires` usa-parks): with it a point in Central Park is
`within` it, without it the national, state and regional answers are the same and local parks are
neither within nor found by search. world-parks is 0.6 MB, but keeping it apart lets the world
pack stay unchanged. The default Geocoder opens installed park packs.

Columns: `id` (unique per row), `park` (the Place id, shared by a park's parcels or zones), `name`,
`tier`, `designation`, `area_km2` (the whole park's), `aliases` (pipe-separated: short name, official
form), `code` (NPS unit code, USFS forest code). Points add `radius_km`, `wikidata`, `sitelinks`.

Ids: `nps:YOSE` (a second unit under one code adds its designation: `nps:DENA:national-preserve`),
`usfs:0505`, `cpcad:<PARENT_ID>` (Banff `cpcad:710300000`), `wikidata:Q192764`, and for PAD-US,
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

## Points without outlines (India and the rest of the world)

Wikidata items with a point and an English label; radius = that of a circle of the item's area
(P2046), capped at 30 km, or 0. They are never `within`: inside the circle they are `near` at 0 km
("in the area of"), beyond it near up to their tier's distance. India has no openly licensed park
outlines (`sources/parks.json` gaps). Parks carry no country: the boundary layers and the worldview
decide it, so no park asserts sovereignty over a disputed area (Wikidata places Deosai and Khunjerab
National Parks, in Gilgit-Baltistan, in Pakistan; that is only used to leave US and Canadian items out).

## Known gaps

- Queen Victoria Park (Niagara Parks Commission) is not in CPCAD; CPCAD has almost no city parks.
- PAD-US Designation layer (wilderness areas) is not read.
