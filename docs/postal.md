# World postcodes

The US, Canada and India packs carry postal *areas* (ZIP Code areas in the optional `usa-zip`,
forward sortation areas, PIN code areas), so a point there is `within` its code. Everywhere else
the optional `world-postal` pack gives postcodes from GeoNames: points, not areas, so a lookup
only ever says a point is *near* a code.

```python
import placewise

r = placewise.lookup(47.378, 8.540)         # Zürich main station
r.postal.name                               # "8001"
r.postal.codes                              # {"place": "Zürich", "country": "CH"}
r.matches["postal"]                         # Match(near, 0.66 km)
r.sources["postal"]                         # "world-postal/postal:nearest"
placewise.find("75007", country="FR")[0]    # Paris 7e's code
placewise.find("SW1A 1AA")[0].place.name    # "SW1A": the UK file has outward codes only
```

Install it with `placewise data install world-postal`, or let auto mode fetch it (add `postal` to
`data.auto_packs`): its `pack.json` lists the countries it covers, so it comes only for those.
Without it lookups answer exactly as before. Rules: `placewise.engine._nearby.postal`; constants:
`placewise.constants.postal`; build: `packbuild.postal` (see `packbuild/README.md`).

## The rule

- A point takes the code of the nearest postcode point **of its own country** (the one the
  worldview reports) within that country's **reach**; a code of the country next door never
  answers, however close.
- The reach is per country, from how densely its points lie: twice the 90th percentile of the
  distance from each point to its nearest neighbour, kept within 2 to 30 km (a few km for German
  or Japanese codes, 30 km for Chinese prefecture codes). A country with a single code (Pitcairn,
  the Falklands) has it everywhere.
- A code covering several places has a point at each (GeoNames lists the code once per place:
  Sydney's 2000 for Sydney, The Rocks, Haymarket ...), so the nearest *place* decides; the
  Place's id carries `:2`, `:3` ... for those other points and `codes["place"]` names the place.
- `Result.matches["postal"]` is always `near`, at the km to the code's point; points that a
  country pack gives a postal area keep it, and disputed ground (where country packs don't name
  places either) gets no code.
- Points are not areas: near the edge of a code's area the nearest point can be the next code's
  (the Eiffel Tower, in 75007, is nearest the point of 75016; the Brandenburg Gate, in 10117,
  nearest the Bundestag's own code 11011, which GeoNames gives a point of its own). Treat the
  code as "the postcode around here", not an address's.

## Search

The name index holds each code once (on its first point), as written and without its spaces or
hyphens: "75007", "10117", "100 00" or "10000" (Czechia), "100-0005" or "1000005" (Japan). A
postcode typed with a space whose whole form matches nothing falls back to its first part, so
"SW1A 1AA" finds the district SW1A and "M5V 3L9" Canada's FSA M5V. Codes repeat across countries
(75007 is also a ZIP Code in Texas): give `country=` to choose.

## Data

GeoNames' postal codes (`allCountries.zip`, CC BY 4.0, rebuilt daily), about 110 countries after
these are left out:

| Left out | Why |
|---|---|
| United States, Canada, India | their country packs carry postal areas |
| Singapore, Portugal | GeoNames documents no source for these files |
| United Arab Emirates | the UAE has no postcode system; the 178,000 codes have no documented source |
| Hong Kong, Macau | no postcodes (999077 and 999078 are placeholders) |
| Northern Ireland (BT codes) | Land and Property Services' terms: internal business use only |
| CEDEX codes (France and its overseas departments), Germany's large-recipient codes (rows named after an organisation, with no accuracy) | business mail, not places |

GeoNames keeps only part of some countries' codes: the UK's outward codes (SW1A) and the
Netherlands' four digits, the first part in Chile, Ireland and Malta, Chinese codes ending in 00,
Argentina's first five characters, Brazil's major codes. A point is the place's coordinates or the
centre of the code's addresses, so it can sit a few km from parts of the code's area. Coordinates
that several codes share as a placeholder (Paris's centre for every arrondissement, beside each
code's own point) are dropped.
