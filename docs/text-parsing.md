# Text locations

`placewise.text` is location search over free text: it reads locations the way listings, profiles
and forms write them, and filters them. It needs no data packs.

Reference data lives in `placewise.constants`; `placewise.text` holds only the code.

| Data | Where | Made by |
| --- | --- | --- |
| ISO 3166-1 countries | `constants/countries/countries.py` | hand, checked against ISO (Debian iso-codes) |
| States, provinces, UK nations | `constants/countries/{usa,can,ind,gbr}/subregions.py` | hand, from USPS / Census, Statistics Canada, ISO 3166-2 |
| Metro and vernacular regions | placewise-data `datasets/regions/*.json` → `constants/countries/regions.py` (and the packs' `regions` polygons) | curated dataset (CC BY 4.0); `python -m packbuild.regions`; regions with `search_as` (GTHA) are read as the region they name |
| City aliases (YYZ, Philly, Saigon) | placewise-data `datasets/cities/aliases.json` → `constants/countries/city_aliases.py` | curated, checked against GeoNames; `python -m packbuild.cities` |
| Known cities (100k+ people, admin1 seats) | `constants/countries/{usa,can,ind,gbr}/cities.py` | GeoNames cities1000 (CC BY 4.0); `python -m packbuild.cities` |
| Names several places share | `constants/countries/ambiguous.py` | hand |
| Remote-scope regions (EMEA, EU, APAC ...) | placewise-data `datasets/country_groups/*.json` → `constants/countries/groups.py`; which groups count: `REMOTE_SCOPE_GROUPS` in `constants/location_text.py` | curated, sourced dataset; `python -m packbuild.country_groups` |
| Currency per country | `constants/countries/currency_codes.py` | Unicode CLDR currencyData; `python -m packbuild.currency_codes` |
| Separators, noise words, placeholders | `constants/location_text.py` | hand |
| Work-mode phrases | `constants/work_modes.py` | hand |

Country folders are named by ISO 3166-1 alpha-3 in lower case; data values stay alpha-2.

```python
from placewise.text import parse_location, LocationFilter, in_country, is_remote_ok_for

parsed = parse_location("Hybrid - Toronto, ON or Remote (Canada)")
parsed.work_mode       # "remote" (the most permissive mode named); work_modes: ("remote", "hybrid")
parsed.remote_scope    # ("CA",)
[(p.city, p.admin1_code, p.country_iso2, p.region) for p in parsed.parts]
# [("Toronto", "ON", "CA", "GTA"), (None, None, "CA", None)]

in_country(parsed, "CA")             # Decision(keep=True, reason="in CA: Toronto, ON")
is_remote_ok_for(parsed, "US")       # Decision(keep=False, reason="remote limited to CA")
LocationFilter.from_dict({"countries": ["CA"], "admin1": ["CA-ON"]}).decide("Montreal, QC")
# Decision(keep=False, reason="not in an allowed location: Montreal, QC (CA; allowed there: CA-ON)")
```

## What a parse returns

`ParsedLocation`: `raw`, `parts`, `work_mode` (`"remote"`, `"hybrid"`, `"onsite"` or None),
`work_modes`, `remote_scope`, `multiple`, `unparsed`.

`LocationPart`: `city` (as written, or the preferred name for an alias), `admin1_code` (without its
country: `ON`, `CA`, `KA`), `admin1_name`, `country_iso2`, `region` (metro id), `confidence`,
`span` (offsets into `raw`), `city_verified`, `remote` (a place a remote listing is limited to),
`place` (the gazetteer's Place), `alternatives` (other readings, less likely). Both types are frozen
and round-trip through `to_dict` / `from_dict`.

## Forms it reads

| Form | Examples |
| --- | --- |
| City, admin1, country | `Austin, TX` · `Austin, Texas, USA` · `Toronto, ON, Canada` · `Pune, Maharashtra` |
| Without commas | `Austin TX` · `Chicago IL USA` · `Ottawa Canada` · `Durham North Carolina` · `WI Madison` |
| Broadest first | `US, CA, Santa Clara` · `US-CA-Menlo Park` · `USA - TX - Austin` · `California - San Francisco` · `US.AZ.Tempe` · `US \| Massachusetts \| Boston` |
| Parentheses | `Austin (TX)` · `HQ (San Francisco, CA)` · `Remote (Canada)` · `Montreal (St. Laurent)` (aside goes to `unparsed`) |
| Abbreviations | `N.Y.` · `D.C.` · `Calif.` · `W. Va.` · `Ont.` · `Que.` · `P.E.I.` · `U.S.` · `U.S.A.` · `UK` · `UAE` |
| Case, spacing, dashes | `SAN FRANCISCO, CA` (title-cased) · `toronto, on` · `Austin,TX` · `Remote – Canada` (any Unicode dash) |
| Several places | `;` · `\|` · `•` · new line · ` or ` · ` and ` · `&` · `/` · `Toronto, ON, Vancouver, BC` · `Austin, Dallas, Houston` |
| Names with "and" | `Trinidad and Tobago` · `Bosnia & Herzegovina` · `Newfoundland and Labrador` stay whole |
| List markers | `Multiple Locations` · `Various locations` · `3 Locations` · `+ 6 others` · `+2 more` · `and 3 more locations` set `multiple` |
| Noise words | Office, HQ, Headquarters, Area, Greater, Metro, Metropolitan, Downtown, Campus, Region, Location(s), Northeast/West Coast ... |
| Site text | `Palo Alto - 1200`, `Fab 10N/X`, `Zone 1`, `Business Tower`, `N/A`, `TBD` go to `unparsed` |
| Metros | `GTA` · `GTHA` · `Greater Toronto Area` · `SF Bay Area` · `SFBA` · `Silicon Valley` · `NYC` · `New York Metro` · `DFW` · `DMV` · `Delhi NCR` · `Greater Vancouver` · `Toronto, GTA` (see `datasets/regions`) |
| City aliases | `NYC` → New York City · `SF` → San Francisco · `LA` → Los Angeles · `Bangalore` → Bengaluru · `Gurgaon` → Gurugram · `Bombay` → Mumbai · airport codes and nicknames (`YYZ`, `PDX`, `Philly`, `NOLA`, `KW` ...) · `North York` → Toronto · `Saigon` → Ho Chi Minh City. A two-letter alias that is also a code (`NY`, `DC`, `SD`) is a city only alone: `NY` is New York City, `NY, USA` the state |
| UK nations | `London, England` · `Edinburgh, Scotland` · `Cardiff, Wales, UK` read England / Scotland / Wales / Northern Ireland as GB's admin1 (`ENG`, `SCT`, `WLS`, `NIR`) |
| Three-letter codes | `CAN`, `SGP`, `PER` in capitals; common ones (`Can`, `Ind`, `Aus` ...) in any case. `Ind.` with its dot is Indiana |
| Postal codes | US ZIP / ZIP+4, Canadian postal codes and Indian PINs are dropped: `Springfield, IL 62701`, `Toronto, ON M5V 2T6` |
| Structured addresses | `parse_address({"addressLocality": ..., "addressRegion": ..., "addressCountry": ...})` (JSON-LD, or city / state / stateCode / country / countryCode keys; `remote=True`) |

## Work modes

| Mode | Phrases |
| --- | --- |
| remote | Remote, Fully Remote, 100% Remote, Remote-first, WFH, Work from home, Telecommute, Virtual, Distributed, Anywhere, Home-based |
| hybrid | Hybrid, Hybrid Remote, in office 3 days/week, 2-3 days per week on-site, 3 days in office, onsite Tuesdays |
| onsite | On-site, Onsite, On site, In office, In-person, Office-based, Non-remote, Not remote, 5 days in office |

Remote scope: `Remote - US`, `US Remote`, `Remote-USA`, `Remote, Canada`, `Remote (Canada)`,
`Canada (Remote)`, `Remote in Canada`, `Remote within the US`, `Remote (US only)`, `Anywhere in the
United States`, `Remote - US and Canada`, `Remote US/Canada`, `Remote - Texas` (`US-TX`), `CA-Remote`
(Canada), and the country groups listed in `REMOTE_SCOPE_GROUPS` (constants/location_text.py), by
any name or alias in the country-group tables: `EMEA`, `North America`, `APAC`, `LATAM`, `Americas` /
`AMER`, `Europe`, `EU` (its current members), `DACH`, `Nordics`, `Benelux`, `ANZ`, `Middle East`,
`MENA`, `Africa`, `NORAM`. The scope holds the group's name (`European Union`, `Nordic countries`).
`Worldwide` / `Global` / `Anywhere` (the World group) mean no limit; `US & Canada` stays two countries. A remote listing with a city (`Remote - San
Francisco, CA`) is limited to that city's subdivision (`US-CA`). An unscoped `Remote` beside a
scoped one adds nothing to the scope.

## Work mode from a description

`detect_work_mode(text, location_hint="", structured=None)` reads a description (HTML or
plain) by statements about the role itself ("This is a hybrid role", "5 days onsite", "#LI-Remote"),
not bare words ("remote sensing", "hybrid bonding"); negations ("remote work will not be
considered") don't count as remote. A source's own value wins: `structured_work_mode("ON_SITE")`
is `"onsite"` (upper, snake and title case spellings; `True` means remote). The phrases are in `constants.work_modes`.

## Ambiguity rules

- A two-letter code counts only as a whole part (after a comma, dash or parenthesis, or a capital
  code peeled off `City ST`). `in` and `on` in prose are words.
- A code that is a state, a province and a country reads in that order: `Smallville, CA` is
  California (0.8) with Canada (0.2) as the alternative; `Amsterdam, NL` is the Netherlands with
  Newfoundland and Labrador as the alternative. The country reading of a state code is kept only
  for codes commonly used for a country (CA, DE, IN, IL, NL, CO, AR, PE, SK and the US territories):
  `Kansas City, MO` is only Missouri.
- Other parts settle a reading (`Kitchener, ON, CA` is Canada), as do `context=`, a known city
  (`Mumbai, MH`, `Atlanta, Georgia`), places elsewhere in the string that are certain
  (`Toronto, ON; London` reads London, Ontario) and the gazetteer.
- Indian state codes count with India in the string, an Indian context or a known city; full names
  always count. Replaced ISO codes (OR, CT, TG, UT) and old names (Orissa) still read.
- A remote listing's lone two-letter code prefers its country: `Remote - CA` is Canada (0.6).
- A region name before a state or province is a city: `Ontario, CA`, `Washington, DC`,
  `Indiana, PA`. Before only its country it stays the region: `Ontario, Canada`.
- `Georgia`: the US state with a US city or a US context, the country with one of its cities
  (Tbilisi ...), 0.5 / 0.5 alone.
- Bare names that several well-known cities share (`London`, `Cambridge`, `Birmingham`,
  `Vancouver`, `Portland`, `Dublin`, `Perth`, `Hyderabad`, `Richmond`) return every candidate with
  a confidence (`constants/countries/ambiguous.py`). `LA` alone is Los Angeles (0.6) or Louisiana (0.4); `New York`
  alone is New York City (0.6) or the state.
- Known cities (the generated GeoNames list and the regions' principal cities) settle which reading
  a code has: `Toronto, CA` is Canada (no Toronto in California), `Mumbai, MH` is Maharashtra,
  `Atlanta, Georgia` the state. A city with only its country gets the admin1 of the one known city
  of that name there: `Ottawa, Canada` is Ontario, `London, UK` England. A reading the text gives
  first still wins when the city fits it: `Richmond, CA` stays California. Known cities never
  place a bare city name.
- Any other bare city keeps no country (confidence 0.5) until a gazetteer is plugged in.

## Gazetteer hook

`parse_location(text, gazetteer=g)` takes any object with
`g.match(city, country_iso2, admin1_code) -> Place | None`. Candidates it confirms win and get
`city_verified=True` and `place`; the rest are dropped. A bare city is looked up with the context
country (or None) and takes its country and admin1 from `place.codes["iso2"]` and
`place.codes["admin1"]`. Site text with a city in it (`Site 4 Taylor, TX`) is searched word
by word.

## Filters

`in_country(parsed, "CA")`, `in_region(parsed, admin1=("ON",), metro=("GTA",))`,
`is_remote_ok_for(parsed, "CA")` and `LocationFilter(...).decide(text_or_parsed)` return a
`Decision(keep, reason)`. `LocationFilter` fields: `countries`, `admin1`, `metros` (which narrow
the countries they belong to), `deny_countries`, `deny_admin1`, `deny_metros`, `remote`
(`any` · `scoped` · `strict` · `deny`), `work_modes`, `unknown` (`keep` · `drop`),
`include_alternatives`. A location with several places passes when any one does.

`currency_for(parsed, default="USD")` infers the currency amounts are likely in: USD
when the US is among the places, else the first country's currency (`constants.countries.CURRENCIES`),
else a city hint (Toronto, Vancouver → CAD; London → GBP; Berlin, Paris → EUR).

## Not yet (needs the gazetteer)

Placing bare cities (`Toronto`, `Geneva`), canonical spellings (`St Paul` → Saint Paul,
`Mclean` → McLean), neighbourhoods to their city beyond the aliases, admin1 for countries without a
table here (Mexico, Australia, Germany ...), and cities inside site text. Several places run together with no separator (`Seattle, WA SF NYC Sunnyvale, CA`)
aren't split.
