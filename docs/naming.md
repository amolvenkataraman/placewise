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
- **locality**: the census place (incorporated place or CDP) containing the point, corrected
  inside a metropolitan area by the **postal city**: the city USPS addresses the point's ZIP Code
  to (the ZCTA's `postal_city`, matched to a census place as `postal_place`; see the US pack),
  used only when that place's boundary is within `POSTAL_CITY_KM` (20 km) of the point.
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

## COD-AB countries (Sri Lanka, Nepal, Bangladesh, Thailand, ...)

One rule (`engine/naming/codab.py`) serves every COD-AB pack, configured per country in
`placewise.constants.codab.COUNTRIES`. The point is looked up once, in the pack's deepest level
(with the `SHORE_KM` snap); the levels above are that unit's parents, so the answers nest (sources
`npl/admin3:polygon`, `npl/admin2:parent`).

- **admin1**: where the world pack's admin1 is the same kind of unit and one has the ADM1's name,
  the world one stays (it has the ISO code; `bgd/admin3:state`); otherwise the ADM1 answers, by
  its COD-AB name (Sri Lanka's provinces, as "Western Province", where Natural Earth has
  districts; Nepal's seven provinces, not the old zones; Viet Nam's 34 provinces after 2025).
- **admin2**: the configured level (district, amphoe, municipio, ilce).
- **locality**: the municipal level where there is one named as people name the place: only
  Nepal's local levels (Kathmandu, Pokhara, Lalitpur). Elsewhere the municipal unit is named
  otherwise than its town (Benito Juarez for Cancun, City of Tshwane for Pretoria) or isn't
  municipal (Sri Lanka's divisional secretariats), and the GeoNames score stays. **city**: the
  GeoNames score.
- **sublocality**: a configured level below (Sri Lanka's Grama Niladhari divisions: Fort,
  Pettah; Thailand's tambon) unless named like the locality or city; in Nepal, the nearest
  GeoNames place inside the municipality.

## Labels

`label.style = "locality"` (the default) gives "<locality>, <admin1>, <country>", falling back to
the city ("San Francisco, California, United States" at SFO); `"city"` leads with the city.
Consecutive repeats drop ("New York, United States"). `label.template` can use `{sublocality}`,
`{locality}`, `{city}`, `{borough}`, `{admin2}`, `{postal}`, `{region}`, `{admin1}`, `{country}`,
`{airport}` and `{water}`. Country names are the ISO short names ("United States"); Natural
Earth's longer form stays in `country.aliases`.

## Known gaps

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
