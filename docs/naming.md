# Naming: three names per point

One "city" field can't serve both "where in town" and "where in the world", so a lookup's
`Result` carries three names, and the label picks among them:

| Field | Meaning | Examples |
|---|---|---|
| `sublocality` | what a local would add | Mission District, Williamsburg, Rouge, Whitefield |
| `locality` | the municipality you are in, corrected for how people talk | Emeryville, Mississauga, Las Vegas (not Paradise) |
| `city` | what you'd tell someone far away | Toronto for Pickering, San Francisco for SFO |

Beside them: `admin2` (county, census division), `borough` (New York City), `postal` (ZIP Code
area, from the optional `usa-zip` pack; forward sortation area, PIN code area; elsewhere the
nearest postcode point of the optional `world-postal` pack, always `near`: `docs/postal.md`) and `regions`
(smallest first). `Result.sources` names
the layer and rule behind every field (`"usa/places:metro"`, `"can/csd:nearest"`).
`Place.type` says what sort of unit a region or admin2 is, so callers needn't read id prefixes:
a region is `"metro"` or `"micro"` (US core-based statistical areas), `"combined"` (US combined
statistical areas), `"cma"` or `"ca"` (Canadian census metropolitan areas and agglomerations) or
`"curated"` (GTA, Bay Area, Delhi NCR); an admin2 is the US county's legal description in lower
case (`"county"`, `"parish"`, `"borough"`, `"census area"` ...), the Canadian census division's
type (`"census division"`, `"regional municipality"`, `"county"`, `"regional district"` ...) or
`"district"` in India.

## How each name was found

`Result.matches` says, for every place field (`country`, `admin1`, `admin2`, `city`, `locality`,
`sublocality`, `borough`, `postal`), how its place relates to the point, so an app needn't parse
`sources`:

| `Match.relation` | Meaning | `distance_km` | Rules (`sources`) |
|---|---|---|---|
| `within` | the place's outline holds the point | 0.0 | `polygon`, `state`, `name`, `worldview` |
| `near` | a fallback chosen by distance or score: the nearest well-known town, a metro's principal city, a postal city, a GeoNames or CGNDB place standing for a rural subdivision, the polygon beside a shore gap | great-circle km to the place's point; to its bounding box where it has none or was taken across a shore gap (within the 1 km margin that is the distance to the polygon) | `score`, `metro`, `postal`, `inside`, `nearest` ... |
| `offshore` | a country or state whose territorial sea (12 nmi) holds the point | km to its box | `offshore` |

`distance_km` is None where it can't be known (a box holding the point but not the outline).
`r.city_within`, `r.locality_within` and `r.city_km` are shortcuts: at the CN Tower the city is
Toronto, `within`, 0 km; on the Alberta prairie it is the nearest town, `near`, tens of km away.
`r.certain` is True when the country and admin1 both hold the point (neither `offshore` nor a
`near` fallback); forward search's `Entity.context_certain` also flags points near a coarse border
(`docs/search.md`, "How sure the context is").
A field an override rule filled with another place has no match; a renamed place keeps its own.
The card (`print(r)`) adds "· 21 km away, not inside" to such lines.

## Borders and islands

The country comes from Natural Earth's 1:10m polygons, which are drawn to about a kilometre: its
Canada takes in downtown Niagara Falls, New York, its Bangladesh the Petrapole checkpoint, and it
has no Treasure Island in San Francisco Bay. Where a country pack is open, its first-level units
decide instead (`placewise.engine._borders`):

- a point inside a US state (Census cartographic boundary, 1:500k), a Canadian province (StatCan
  cartographic boundary) or an Indian state (the India pack's) that belongs to another country than
  Natural Earth's takes that country, with `sources["country"]` the unit layer's
  (`"usa/states:polygon"`) and `matches["country"]` `within`; admin1 and the lower levels follow
  from that country's pack as anywhere else;
- the US and Canadian units are clipped to the shoreline, so a point inside one where Natural Earth
  has no country (an island it leaves out) is on land: the country is the unit's, and the sea
  around it is `near`, not "On San Francisco Bay". India's states, unions of PIN-code areas that
  take in lagoons, only correct land borders;
- where Natural Earth's own country's pack also holds the point (two packs' borders overlapping
  by metres), or the point is less than 50 m inside the unit (within the unit's own
  generalisation: the brink of the Horseshoe Falls), Natural Earth's answer stands; where two other
  packs both hold it, the unit the point lies deeper inside wins;
- disputed areas are left exactly as before (`docs/worldviews.md`): no correction inside a
  worldviews area, and none from units only India's view gives India (`india_view_only`).

## Regions

`regions` lists every region containing the point, smallest first by area: the pack's curated
`regions` layer (Greater Toronto Area, San Francisco Bay Area, Delhi NCR; they may overlap) and
the statistical metro areas beside them (US CBSA and CSA, Canada's CMA or CA), which name every
metro, curated or not. Fort Erie: St. Catharines - Niagara (CMA), Greater Golden Horseshoe.
Pearson: Toronto (CMA), Greater Toronto Area, GTHA, Greater Golden Horseshoe. The roll-up rules
below always read the CBSA and CMA, whichever region comes first.

The rules live in `placewise.engine.naming` (one module per country, pure rules in `rules.py`) and
their thresholds in `placewise.constants.naming`. They are starting points, tuned against the
public places in `tests/e2e/test_e2e_golden.py` and `tests/e2e/test_e2e_naming.py`.

## Where the rules apply

A country pack names a point only when the world pack places the point in that country (after
the worldview order, `docs/worldviews.md`) and its admin1 isn't coded for another country; everywhere else, and with no
country pack installed, the answer is the world one: `locality` and `city` are both the GeoNames
city score (`placewise.engine._cities`), with no sublocality. So a US county that spills across
the Niagara River never names a point on the Canadian side.

**Town and city outlines** (the optional `world-towns` pack, `placewise.engine.naming.towns`).
Outside the US, Canada and India (whose packs win, and which the pack leaves out), a point inside
one of its GHS-SMOD outlines (an urban centre or a town, cut at the borders, named after the most
populous GeoNames place inside: packbuild/README.md, "World-towns pack") in the outline's own
country (as the worldview reports it) takes its names from it:

- `locality`: the city score's place when that place is in the same outline (Puteaux, inside
  Paris' outline), else the outline's place (a village whose own outline the score passed over
  for the bigger town nearby);
- `city`: the outline's place, unless the locality doesn't roll up into it (`rolls_up`, the
  roll-up rule of the country packs: 100,000+ people, or not ten times smaller), so Yokohama
  stays Yokohama inside the Tokyo-Yokohama outline.

A field the outline names comes from `world-towns/towns:polygon` (`matches`: within); the others
keep the score's. Outside the outlines, and without the pack, the answer is the city score's.

Census and StatCan shapes are clipped to the shoreline. A point within `SHORE_KM` (1 km) of a
shape but in none (a pier, Horseshoe Falls) takes the nearest one, with rule `nearest`.

## United States (Census Bureau pack)

- **admin1**: the county's state (`usa/counties:state`), finer than Natural Earth's line.
- **locality**: the census place (incorporated place or CDP) containing the point, corrected
  inside a metropolitan area by the **postal city**: the city USPS addresses the point's ZIP Code
  to (the ZCTA's `postal_city`, matched to a census place as `postal_place`; see the US pack;
  the usa pack's `postal_cities` carries it, so this works without `usa-zip`), used only when that place's boundary is within `POSTAL_CITY_KM` (20 km) of the point.
  - An incorporated place is always itself (Emeryville stays Emeryville, Brooklyn's ZIP Codes
    don't make New York "Brooklyn").
  - A CDP takes its postal city when that is an incorporated place: the Strip and Harry Reid
    Airport (Paradise), South Point (Enterprise) and Dadeland (Kendall) are Las Vegas, Las Vegas
    and Miami. The CDP becomes the sublocality.
  - Unless the CDP's name extends the postal city's name (`rules.extends`): East Los Angeles
    (ZIP Code city Los Angeles) stays East Los Angeles, with Los Angeles as its city. Its name
    already says where it is, and it is a place people name.
  - A postal city that is another CDP replaces only a CDP of fewer than `CDP_KEEP_POPULATION`
    (5,000) people (the design's "CDP of 5,000+ people stays"): The Woodlands (121,000, addressed
    Spring) and Tysons (addressed McLean) stay. Arlington VA, Bethesda, Columbia MD, Reston and
    Stanford are their own postal cities and stay.
  - Unincorporated land (no census place) takes its postal city: SFO is San Francisco (94128),
    MSP is Minneapolis, Mount Rushmore Keystone, the Kennedy Space Center visitor complex Merritt
    Island. With no postal city (no ZCTA, a name that is no census place such as Universal City,
    or outside a metro) it has no locality.
  - Outside metropolitan areas (micropolitan areas and rural counties) the census place stands:
    a ZIP Code there names a post office that can be a town 30 km away.
- **city**: the locality; for a CDP that keeps its name, its incorporated postal city (East Los
  Angeles -> Los Angeles). With no locality, the metro's largest principal city in the point's
  state (OMB delineation list 2, `cbsa.principal_cities`) when its boundary is within
  `METRO_CITY_KM` (25 km; Universal Studios Hollywood -> Los Angeles), else the GeoNames score. An
  incorporated place is always its own city (Emeryville stays Emeryville; the design page's
  "metro principal city" roll-up for small incorporated cities is not applied).
- **sublocality**: the nearest GeoNames place within `SUBLOCALITY_KM` (2 km) whose point lies in
  the same census place and isn't named like the locality, city or borough.
- **borough**: New York City's five counties (Kings -> Brooklyn). **admin2**: the county.
  **postal**: the ZCTA. **regions**: curated, CBSA and CSA (see Regions).

## Canada (StatCan pack)

- **admin1**: the census subdivision's province (`can/csd:state`).
- **locality**: the census subdivision (CSD), so amalgamated cities come out whole (Rouge Park
  and Scarborough are in Toronto; Pearson is in Mississauga). Rural CSDs (townships, rural
  municipalities, parishes: `CSD_RURAL`) and unorganised ones (improvement districts, unorganised
  territory: `CSD_UNORGANIZED`) are named by the nearest CGNDB settlement inside them within
  `CGNDB_LOCALITY_KM` (4 km; hamlets, communities, villages: `CGNDB_LOCALITY_TERMS`), which names
  Lake Louise (Improvement District No. 9), else by
  the nearest GeoNames place inside them within `RURAL_PLACE_KM` (8 km); failing both, a rural
  CSD is named itself and an unorganised one not at all. A CGNDB place has no population, so it is
  its own city.
- **city**: the locality when it has `CITY_KEEP_POPULATION` (100k) people or is named in its CMA
  (Kitchener, Cambridge, Waterloo); otherwise the CMA's first city in the same province when that
  one is `CITY_ROLL_UP_RATIO` (10) times bigger: Pickering (99k) -> Toronto, Fort Erie stays (St.
  Catharines is only 4x bigger). A CMA split by a provincial border (Ottawa - Gatineau) has one
  feature per province, and each part's first city is the first one named in that province.
- **sublocality**: where the locality is the CSD itself, a CGNDB neighbourhood or community
  inside it (`CGNDB_SUBLOCALITY_TERMS`: urban communities, neighbourhoods, communities, boroughs,
  former villages), not named like the locality or city: each reaches `CGNDB_SUBLOCALITY_KM` from
  its point by its map scale (4 km for names shown from 1:700,000, such as Scarborough, Kanata,
  Etobicoke; 2.5 km from 1:250,000; 1.5 km for a street's few blocks: Malton, Port Credit,
  Yorkville), and the point takes the one it is deepest inside (distance over reach). Failing
  that, the nearest GeoNames place as in the US (Rouge). **admin2**: the census division (from
  the CSDUID). **postal**: the FSA. **regions**: curated, and the CMA or CA.

## India (India pack)

The India pack's `states`, `districts` and `cities` are unions of PIN code areas keyed to the
Local Government Directory (LGD; packbuild/README.md, India pack). A pack built before them falls
back to the PIN areas alone.

- **admin1**: the `states` feature's state (`ind/states:polygon`; ISO 3166-2:IN after 2023, mapped
  to the world pack's older codes such as IN-OR for Odisha). Gurugram is in Haryana even where
  Natural Earth's coarse line says Delhi, and the city score, which halves cities of another
  admin1, then picks Gurugram. Without `states`: the PIN area's state (`ind/pincodes:state`).
- **admin2**: the LGD district, with the name in use (Gurugram, Mysuru, Chhatrapati Sambhajinagar).
- **locality** and **city**: the `cities` feature, an urban local body drawn as its PIN areas
  (Bengaluru as the former BBMP area, Delhi's reunified corporation, New Delhi's NDMC, Navi
  Mumbai); a point in no city polygon (towns whose PIN areas are big and rural) takes the GeoNames
  score.
- **sublocality**: the nearest `neighbourhoods` point of the point's city within 1.5 km, one of
  its own PIN area first (a post office's name: "Koramangala S.O" -> Koramangala; institutions such
  as courts and colleges are left out); else the PIN area's post office name before its type word
  ("Whitefield S.O" -> Whitefield, "Gandhi Bazar SO Amritsar" -> Gandhi Bazar), unless it is the
  city's own name.
- **postal**: the PIN code area.
- Features flagged `india_view_only` (PIN areas and units on ground only India's view puts in
  India) answer only when the IN worldview decided the country (docs/worldviews.md).

## Airports

`Result.airport` is the airport the point is at or near, from OurAirports (large and medium
airports, and small ones with scheduled service), with its distance and bearing. Without airport
footprints, two rules stand in for "the airport here" (constants in `placewise.constants.lookup`):

1. **At.** The point is `at` an airport within a radius that follows the airport's OurAirports
   size: 2.5 km of a large airport's reference point, 1 km of a medium one's, 0.5 km of a small
   one's. Any airport counts, with or without scheduled service (a point on Begumpet's apron is at
   BPM). The 1 km keeps the downtown blocks beside a city airport out: Toronto's Harbourfront is
   1.6 km from Billy Bishop (YTZ), near it, not at it.
2. **Near.** Otherwise it is the airport you would fly from: among airports with scheduled service
   (`near.airport_scheduled = true`) in reach (`near.airport_large`, 40 km, for large airports;
   `near.airport`, 10 km, for the others), the smallest distance times a size weight (large 1,
   medium 3, small 6). A large airport wins unless a smaller one is three times nearer: from
   Hyderabad's centre HYD (22 km), not Begumpet (no scheduled service); from Hillsdale in San Mateo
   SFO (11 km), not San Carlos (5 km); from the CN Tower Billy Bishop (1.8 km), not Pearson
   (23 km). Belmont, 2.3 km from San Carlos, gets San Carlos.

`near.airport_scheduled = false` lets any airport be near; `near.airport = 0` leaves only large
airports. An override `tune` rule for the kind `airport` with `near_km` sets every airport's reach.
Packs built without OurAirports' `type` read every airport as medium, without `scheduled` as
served. Airport outlines (OSM aeroway areas, or boxes from runway ends) would replace the radius;
they are a future data item.

## Time zones

`Result.tz` is the IANA zone of the point: on land and within the territorial sea (12 nmi), from
the zones the packs give their admin units (`placewise.engine._timezones`), else the nearest
city's. Farther out at sea it is the nautical zone of the longitude, 15-degree bands centred on
multiples of 15 degrees (UTC-10 from 157.5 W to 142.5 W), named as tzdb's fixed zones with their
inverted sign (`Etc/GMT+10` for UTC-10, `Etc/GMT` for UTC), and `sources["tz"]` is
`"nautical:longitude"` so a caller can tell it from a land zone. Ships and aircraft keep other
times in practice; this is the zone a local date at sea is usually computed in.

## Batches

`lookup_many` takes any number of points. Exactly repeated points are looked up once; the
distinct ones run through the steps in passes of at most 10,000 points with `near` (50,000
without), so the per-point working arrays stay bounded however big the batch
(`placewise.constants.lookup.CHUNK_POINTS_NEAR`, `CHUNK_POINTS`). Measured with all 14 packs on
points near cities, after the indexes were built: a 100,000-point batch with `near` peaked 1.1 GB
above its starting memory in one pass and 0.16 GB (the Results themselves) in passes, and ran
faster (2,950 points/s instead of 1,900). What remains is the indexes the parks, water, notable
and postal packs build on first use, per region a batch touches (about 1.5 GB for all of them),
which no batch size changes; `near=False` skips most of them.

## Labels

`label.style = "locality"` (the default) gives "<locality>, <admin1>, <country>", falling back to
the city ("San Francisco, California, United States" at SFO); `"city"` leads with the city.
Consecutive repeats drop ("New York, United States"). `label.template` can use `{sublocality}`,
`{locality}`, `{city}`, `{borough}`, `{admin2}`, `{postal}`, `{region}`, `{admin1}`, `{country}`,
`{within}`, `{airport}` and `{water}`.

Rules on top of that, in order:

1. **Parks.** Inside a national or state-level park (tier 1 or 2, docs/parks.md) the park says more
   than the state and country, so the label is "<locality>, <park>" ("Yosemite Valley, Yosemite
   National Park", "Lake Louise, Banff National Park"). Without a locality the city leads only
   when its point lies in the park's box (the GeoNames place "Yosemite Valley"), else the park
   stands alone ("Yosemite National Park" in the backcountry): a city found 30 km away would name
   a town outside the park. With `label.style = "city"` the city leads instead. The park is the
   most significant one the point is in (`within[0]`). National forests and grasslands don't
   count: their administrative boundaries take in whole towns (South Lake Tahoe lies in the Lake
   Tahoe Basin Management Unit). Turn the rule off with `label.parks = false`; a template ignores it.
2. **Water.** On a sea or lake the label names the water ("On Lake Tahoe"; "Over Lake Ontario" given an altitude,
   docs/water.md), park or not.
3. **Offshore.** Far from land: "Offshore, 15 km S of Toronto". Country names are the ISO short names ("United States"); Natural
Earth's longer form stays in `country.aliases`.

## Known gaps

- Outside the US, Canada and India the admin1 is Natural Earth's unit. Its level isn't always
  ISO 3166-2's first level: France's departments (Seine-et-Marne) and Italy's provinces (Milan)
  stand where the regions (Île-de-France, Lombardy) are the first level, and the UK and Ireland
  have counties. World packs built after 2026.11.1 carry each unit's `region` and `region_code`
  (Natural Earth's; for France and Italy the ISO region, FR-IDF, IT-25), so a later placewise can
  answer the region as admin1 with the department as admin2. Those packs also take Natural
  Earth's English names (North Holland, North Rhine-Westphalia, Basra) with a curated list of
  corrections (placewise-data `datasets/names/admin1.json`), keeping the local name
  (`name_local`) for search; the 2026.11.1 pack has the local names, and Natural Earth's typo
  "Seien-et-Marne".
- US postal cities are ZIP Code Business Patterns' and GeoNames' names, not USPS's own file
  (copyrighted and sold per copy), and a ZCTA is only an approximation of a ZIP Code. A postal
  name that is no census place (Universal City, Yosemite National Park, Brooklyn) is never a
  locality. Hawaii's census name "Urban Honolulu" is used as is.
- The East Los Angeles rule is a judgement: CDPs people name in their own right but whose names
  don't extend the postal city (Kendall, White Center) take it (Miami, Seattle) and keep the CDP
  as their sublocality.
- New England towns and other county subdivisions are not in the pack yet: a point in a town with
  no census place has no locality.
- No urban-area test for roll-ups: a whole CMA counts, so a rural CSD at a CMA's edge can roll up.
- India's cities are postal approximations: a big fringe PIN area of a city stays out of it, and
  a satellite city keeps its own name as the city (Salt Lake answers Bidhannagar, not Kolkata).
- Parks, water and notable places are not named yet. India has curated regions only (no
  statistical metro areas).
