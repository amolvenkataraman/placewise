# Water

With the `world-water` pack installed, a lookup says what water a point is on, or beside:

```python
import placewise

placewise.lookup(43.6, -77.9).label            # "Over Lake Ontario"
placewise.lookup(39.0968, -120.0324).label     # "On Lake Tahoe"
placewise.lookup(50.0, -30.0).label            # "Over the North Atlantic Ocean"
r = placewise.lookup(50.0, -30.0)
r.water                                        # Nearby(North Atlantic Ocean, over, 1,180 km to shore)
placewise.lookup(25.3069, 83.0107).near        # (..., Nearby(Ganges, near, 0.9 km), ...)
```

The pack is optional (`placewise data install world-water`); without it lookups answer exactly
as before. Rules: `placewise.engine._water`; constants: `placewise.constants.water`; build:
`packbuild.water` (see `packbuild/README.md`, "Water pack").

## On water

| | When | `Result.water` | Label |
|---|---|---|---|
| a lake or reservoir | inside its outline, at least the shore margin from its shore (0.1 km for HydroLAKES and Global Dam Watch outlines, 0.5 km for Natural Earth's); a lake answers before a reservoir drawn over it | the lake, `on` (`over` for lakes of 10,000 km² or more), distance and bearing to the nearest shore | "On Lake Tahoe", "Over Lake Ontario" |
| a sea or ocean | in no country polygon, at least 1 km from the nearest, inside a marine polygon (or within 25 km of one: the slivers Natural Earth's coarse coast leaves) | the sea, `over`, distance and bearing to the nearest coast | "Over the Arabian Sea"; far offshore with the old reference kept: "Over the Pacific Ocean, 15 km S of ..." |

- On a lake, country, admin1, city and the other fields stay as on land: only the label and
  `water` change. Within 12 nmi of a coast the country stays too (as before); the label then names
  the sea alone.
- Far offshore, `water` used to hold the nearest country (`offshore`); when a marine polygon
  answers, that entry moves to `near`, so nothing is lost.
- Closer to the shore than the margin, a point counts as on land (a pier, a harbour, a beach: the
  1:10m coast is off by hundreds of metres in places), and the water is `near` instead.
- "the": seas, oceans, straits, channels, fjords, reefs and rivers take it ("the Kattegat", "the
  Ganges"), as do names like "Persian Gulf", "Bay of Bengal", "Hirakud Reservoir"; lakes, bays and
  sounds don't ("Lake Tahoe", "Hudson Bay", "Puget Sound").

## Near water

For points on land, `Result.near` gains up to three `near` entries (with `place.kind` "water"),
merged with the notable cities by distance. The distance is to the feature's nearest edge; there
is no bearing.

| | Near within |
|---|---|
| a sea or ocean (marine polygon edge) | 5 km |
| a lake of 10,000 km² or more (the Great Lakes) | 5 km |
| a lake of 100 km² or more | 2 km |
| a lake of 10 km² or more | 1 km |
| a smaller lake | 0.3 km |
| a river (Natural Earth centerline, about 1 km from either bank) | 2 km |

Each `Place` has `kind` "water", `codes["type"]` (ocean, sea, gulf, bay, strait ..., lake,
reservoir, river, canal) and `codes["wikidata"]` where known; its id is `wikidata:Q...` where the
Wikidata id is unique, else the source's (`ne:<ne_id>`, `hydrolakes:<Hylak_id>`).

## Data

| Layer | Source | Licence |
|---|---|---|
| `marine` | Natural Earth 1:10m `geography_marine_polys`: 294 named seas, gulfs, bays, straits and ocean halves | public domain |
| `lakes` | HydroLAKES v1.0, lakes of 10 km² or more, simplified to 30 m, named from Natural Earth, then Wikidata, then HydroLAKES; plus Natural Earth's lakes HydroLAKES doesn't cover | CC BY 4.0, public domain, CC0 |
| `reservoirs` | Global Dam Watch v1.0 reservoirs of 10 km² or more with a name, simplified to 30 m, that no named lake covers (the Tehri reservoir; Lake Mead and Hirakud are named HydroLAKES outlines already) | CC BY 4.0 |
| `rivers` | Natural Earth 1:10m river centerlines with the North America and Europe supplements | public domain |

- **Lake country.** HydroLAKES' `Country` field is the country of the lake's outflow (Lake Ontario
  is "United States of America"), so it is not used: a lake's country is the world pack's, with
  the worldview applied. Water names themselves don't change with the worldview yet.
- **Rivers** are stored as zero-area polygons (each line traced out and back), so a polygon
  layer's boundary distances measure the distance to the line; this stands in for line layers.
- **Unnamed lakes** are left out: there is nothing to call them. About 90% of HydroLAKES' lakes of
  10-100 km² have no name in any of the three sources.
- **Reservoirs** are read exactly like lakes (on, near, search), from their own layer. A Global Dam
  Watch reservoir is named by its own name ("Lake Mead"), else its dam's without "Dam", adding
  "Reservoir" where the name doesn't say it is water ("Tehri" -> "Tehri Reservoir"). A natural
  lake behind a lake-control dam (Lake Tahoe) stays a lake, and a reservoir a named lake already
  covers (half its area or more) is left out, so a water body answers once.

### Rejected

| Dataset | Why |
|---|---|
| Marine Regions IHO Sea Areas v3 | CC BY-NC-SA 4.0 (the download form says so; it was once listed here as CC BY): non-commercial and share-alike. Natural Earth's public-domain marine polygons cover the same need. Registry id `marineregions-iho` is on the deny list. |
| HydroRIVERS | The HydroSHEDS v1 licence forbids stand-alone redistribution and needs a pass-through end-user licence and an indemnity; it also has no river names. Registry id `hydrorivers` is on the deny list. |

Not yet: Marine Regions EEZs ("in Indian waters"), per-worldview
sea names (Persian Gulf / Arabian Gulf, Sea of Japan / East Sea; Natural Earth's alternatives are
kept as `aliases`), named coasts, and OpenStreetMap water in a share-alike pack.
