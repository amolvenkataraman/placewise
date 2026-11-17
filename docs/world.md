# Countries, subdivisions, groups and profiles (`placewise.world`)

`placewise.world` answers questions about countries rather than points: which country a code or
name means, which countries are in a group (on a given date), a country's subdivisions, and a
country's profile (currency, calling code, conventions ...). It holds no data itself:

| What | Where it comes from |
|---|---|
| ISO 3166-1 countries | `constants/countries/countries.py` (all 249 codes) |
| Subdivisions (ISO 3166-2) | `constants/countries/{usa,can,ind,gbr}/subregions.py` |
| Country groups, memberships with dates | `datasets/country_groups/*.json` → `constants/countries/groups.py` (`python -m packbuild.country_groups`) |
| Metro regions | `datasets/regions/*.json` → `constants/countries/regions.py` |
| Profiles | the world pack's `country_facts` layer (GeoNames, Unicode CLDR, Wikidata; `packbuild.country_profiles`) |

Everything but profiles works offline from the package; profiles need the world data pack
(`placewise data install world`).

## Countries

```python
from placewise import world

world.country("can").alpha2          # "CA"; alpha-2, alpha-3, numeric (124 or "124"), name or alias
world.country("U.S.").official_name  # "United States of America" (None where no source gives one)
world.country("Canda")               # KeyError: no country 'Canda'; did you mean 'Canada'?

world.countries()                                # all 249, sorted by name
world.countries(group="US & Canada")             # [Canada, United States]
world.countries(group=["EU", "NATO"])            # a list means every group: EU members in NATO
world.countries(group="EU", continent="Europe")  # filters combine
world.countries(kind="currency-union")           # in any group of that kind
world.countries(group="EU", as_of="2019-06-01")  # includes GB; as of 2021-01-01 it doesn't
```

`group` takes a group id (`legal:eu`), name or alias in any case (`EU`, `EMEA`, `Western Europe`,
`CANZUK`, `Schengen`). `continent` takes a continent group (`Europe`, `oceania`); continents follow
the seven-continent convention with UN M49 assignments, so Cyprus is in Asia. `as_of` is a
`datetime.date` or `"YYYY-MM-DD"` and defaults to today. Dates given as a year alone cover the
whole year (a member `since 1949` counts from 1949-01-01, `until 2000` to 2000-12-31). `placewise.country`
and `placewise.countries` are the same functions.

## Groups

```python
eu = world.group("EU")             # CountryGroup: id, name, aliases, kind, category, members, source, notes
eu.members                         # Membership(country, since, until, suspended_since) for every member, past ones too
world.group("G20").other_members   # ("legal:eu", "legal:african-union"): members without an ISO code

world.groups(of="CA", category="legal")       # CUSMA, G7, NATO, Five Eyes, CANZUK, OECD, Commonwealth ...
world.groups(kind="alliance")
world.members("EU")                           # the 27 member countries today
world.members("EU", as_of="2019-06-01")       # 28, with GB
world.is_member("NO", "Schengen")             # True
world.is_member("GB", "EU", on="2019-06-01")  # True
```

`category` is `geographic` (continents, UN M49 regions, business regions like EMEA and APAC,
common groupings like DACH) or `legal` (unions, treaty areas, trade agreements, alliances ...).
Geographic groups are undated. `World` (aliases `Worldwide`, `Global`, `Anywhere`) has every country.

## Subdivisions

```python
world.subregions("US")                       # 50 states, DC (kind "district") and 5 territories
world.subregions("IN", kind="union territory")
world.subregion("CA-ON").name                # "Ontario"
world.subregion("Ontario").code              # "CA-ON"
world.subregion("ON", country="CA").codes    # {"sgc": "35"}; US states carry {"fips": ...}
world.subregion("AR")                        # KeyError: ambiguous: US-AR, IN-AR; pass country=
world.subregions("FR")                       # LookupError: subdivisions of France are not available yet
```

Tables exist for the United States, Canada, India and the United Kingdom (its four countries:
England, Scotland and Wales are ISO "country", Northern Ireland "province"). Other countries raise
`LookupError` rather than return an empty list.

## Metro regions

```python
world.regions("CA")   # curated metro and vernacular regions (GTA, Greater Vancouver ...), by name
```

## Profiles

```python
ca = world.profile("CA")            # or placewise.profile("CA")
ca.currency                         # Currency(code="CAD", name="Canadian Dollar", symbol="CA$", narrow_symbol="$")
ca.calling_code                     # "+1"
ca.measurement_system               # "metric" ("US" for the US, "imperial-mixed" for the UK)
ca.driving_side, ca.first_day_of_week, ca.date_format   # "right", "sunday", "y-MM-dd" (CLDR pattern, locale en-CA)
ca.languages, ca.time_zones         # BCP 47 tags, IANA zones
ca.population                       # Statistic(value=41651653, source="geonames", year=None)

world.profile("CA-ON")              # a subdivision: only the country-wide facts (currency, conventions ...)
world.profile("CA", pack="path/to/world-2026.11")   # an explicit pack instead of the installed one
```

Fields: `code`, `name`, `kind`, `alpha2`, `alpha3`, `capital`, `continent`, `currency`,
`calling_code`, `languages`, `measurement_system`, `driving_side`, `first_day_of_week`,
`date_format` (with the CLDR `locale` it comes from), `tld`, `time_zones`, `population` and
`area_km2` (each with source and year), `neighbours`, `postal_code_format`, `postal_code_regex`.
A value no source has is `None` (or empty); nothing is filled in by hand. GeoNames gives no
reference year for its population and area figures, so `year` is `None`.

Sources: GeoNames countryInfo.txt and timeZones.txt (CC BY 4.0), Unicode CLDR 49 via the cldr-json
packages (Unicode License v3: currency per territory, English currency names and symbols,
measurement system, first day of the week, the short date pattern of each territory's likely
locale), Wikidata (CC0: driving side). The continent is the package's own, so it agrees with
`countries(continent=...)`. Without an installed world pack (and offline), `profile` raises
`LookupError` naming `placewise data install world`.

All models are frozen dataclasses with `to_dict` / `from_dict` (`placewise.model`).
