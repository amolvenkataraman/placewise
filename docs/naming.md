# Naming: three names per point

One "city" field can't serve both "where in town" and "where in the world", so a lookup's
`Result` carries three names, and the label picks among them:

| Field | Meaning | Examples |
|---|---|---|
| `sublocality` | what a local would add | Mission District, Williamsburg, Rouge, Whitefield |
| `locality` | the municipality you are in, corrected for how people talk | Emeryville, Mississauga, Las Vegas (not Paradise) |
| `city` | what you'd tell someone far away | Toronto for Pickering, San Francisco for SFO |

Beside them: `admin2` (county, census division), `borough` (New York City), `postal` (ZIP Code
area, forward sortation area, PIN code area) and `regions` (smallest first). `Result.sources` names
the layer and rule behind every field (`"usa/places:metro"`, `"can/csd:nearest"`).

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

Census and StatCan shapes are clipped to the shoreline. A point within `SHORE_KM` (1 km) of a
shape but in none (a pier, Horseshoe Falls) takes the nearest one, with rule `nearest`.

## United States (Census Bureau pack)

- **admin1**: the county's state (`usa/counties:state`), finer than Natural Earth's line.
- **locality**: the census place (incorporated place or CDP) containing the point.
  - A CDP within `METRO_CDP_KM` (5 km) of its metro's principal city, the CBSA title's first city
    in the same state, takes that city, unless the CDP is itself named in the title: the Strip
    (Paradise CDP) is Las Vegas, East Los Angeles is Los Angeles; Arlington VA (in the title) and
    Stanford (16 km out) stay. The CDP becomes the sublocality. This stands in for the design's
    "ZIP Code's postal city" rule: the pack has no postal-city names (ZCTAs are areas without
    names), and an unincorporated suburb next to the principal city is usually addressed by it.
  - Unincorporated land (no census place) has no locality.
- **city**: the locality. On unincorporated land, the metro's principal city when its boundary is
  within `METRO_CITY_KM` (25 km; SFO -> San Francisco), else the GeoNames score. An incorporated
  place is always its own city (Emeryville stays Emeryville; the design page's "metro principal
  city" roll-up for small incorporated cities is not applied).
- **sublocality**: the nearest GeoNames place within `SUBLOCALITY_KM` (2 km) whose point lies in
  the same census place and isn't named like the locality, city or borough.
- **borough**: New York City's five counties (Kings -> Brooklyn). **admin2**: the county.
  **postal**: the ZCTA. **regions**: curated, CBSA and CSA (see Regions).

## Canada (StatCan pack)

- **admin1**: the census subdivision's province (`can/csd:state`).
- **locality**: the census subdivision (CSD), so amalgamated cities come out whole (Rouge Park
  and Scarborough are in Toronto; Pearson is in Mississauga). Rural CSDs (townships, rural
  municipalities, parishes: `CSD_RURAL`) and unorganised ones (improvement districts, unorganised
  territory: `CSD_UNORGANIZED`) are named by the nearest GeoNames place inside them within
  `RURAL_PLACE_KM` (8 km); failing that, a rural CSD is named itself and an unorganised one not
  at all.
- **city**: the locality when it has `CITY_KEEP_POPULATION` (100k) people or is named in its CMA
  (Kitchener, Cambridge, Waterloo); otherwise the CMA's first city in the same province when that
  one is `CITY_ROLL_UP_RATIO` (10) times bigger: Pickering (99k) -> Toronto, Fort Erie stays (St.
  Catharines is only 4x bigger). A CMA split by a provincial border (Ottawa - Gatineau) has one
  feature per province, and each part's first city is the first one named in that province.
- **sublocality**: as in the US, inside the same CSD. **admin2**: the census division (from the
  CSDUID). **postal**: the FSA. **regions**: curated, and the CMA or CA.

## India (India Post pack)

There are no open municipal or state polygons for India yet, so:

- **admin1**: the PIN area's state (`ind/pincodes:state`; ISO 3166-2:IN after 2023, mapped to the
  world pack's older codes such as IN-OR for Odisha). Gurugram is in Haryana even where Natural
  Earth's coarse line says Delhi, and the city score, which halves cities of another admin1, then
  picks Gurugram.
- **locality** and **city**: the GeoNames score.
- **sublocality**: the PIN area's post office name before its type word ("Whitefield S.O" ->
  Whitefield, "Gandhi Bazar SO Amritsar" -> Gandhi Bazar), unless it is the city's own name.
- **postal**: the PIN code area.

## Labels

`label.style = "locality"` (the default) gives "<locality>, <admin1>, <country>", falling back to
the city ("San Francisco, California, United States" at SFO); `"city"` leads with the city.
Consecutive repeats drop ("New York, United States"). `label.template` can use `{sublocality}`,
`{locality}`, `{city}`, `{borough}`, `{admin2}`, `{postal}`, `{region}`, `{admin1}`, `{country}`,
`{airport}` and `{water}`. Country names are the ISO short names ("United States"); Natural
Earth's longer form stays in `country.aliases`.

## Known gaps

- Lake Louise (in Improvement District No. 9, Banff National Park) gets no locality: GeoNames
  cities1000 has no place there. A StatCan designated-place or population-centre layer would fix
  it.
- The US postal city is approximated (above); the design's "CDP of 5,000+ people stays" can't be
  applied because the Census places layer has populations for incorporated places only.
- No urban-area test for roll-ups: a whole CMA counts, so a rural CSD at a CMA's edge can roll up.
- India's localities are GeoNames places, which sometimes prefer a taluk or village over the city
  (Fort Kochi answers Kanayannur).
- Parks, water and notable places are not named yet. India has curated regions only (no
  statistical metro areas).
