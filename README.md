# placewise

Offline, two-way geocoding and a one-stop geo toolkit. Given a point it answers the way a person
would (the city you'd say, the region, the park or lake you were in, the airport you were at);
given a name it returns where that is. Everything runs locally: the code installs from PyPI, and
the data downloads on first use as versioned, checksummed packs (about 1 GB for the world plus
full detail for a few countries).

It is built for everyone from someone who just wants their Yosemite photos to GIS professionals:
plain words on the simple path, precise terms (EPSG codes, ellipsoids, error bounds) one step away.

**Status: early development.** Reverse lookup works on the world pack (countries, states and
provinces, 172k cities, time zones, airports, worldviews) and, where they are installed, the US,
Canada and India packs, with the first naming rules (`docs/naming.md`): three names per point
(sublocality, locality, city), county or census division, NYC borough, ZIP Code area / FSA / PIN
code and metro areas. With the optional `world-water` pack, points on water name it ("Over Lake
Ontario", "On Lake Tahoe", "Over the North Atlantic Ocean") and points beside a sea, lake or river
list it in `near` (`docs/water.md`). Parks (`docs/parks.md`: `within` and nearby parks from the usa-parks, can-parks and world-parks
packs) too. Curated regions are next. The toolkit, tracks, privacy
tools, data store, overrides, config and the server are done.

```python
import placewise

r = placewise.lookup(43.6426, -79.3871)       # downloads the world pack on first use
r.label                                       # "Toronto, Ontario, Canada"
r.admin1.codes, r.tz, r.airport               # ISO codes, "America/Toronto", Nearby(YTZ, 1.8 km)
placewise.Geocoder().lookup_many(lats, lons)  # vectorised, ~30k points/s
placewise.lookup(35.9208, 74.3089, worldview="IN").label   # "Gilgit, Ladakh, India" (docs/worldviews.md)

r = placewise.lookup(36.1147, -115.1728)      # with the US pack installed: the Las Vegas Strip
r.locality.name, r.sublocality.name           # "Las Vegas", "Paradise" (the census place)
r.postal.name, r.admin2.name                  # "89109", "Clark County"
```

The same lookups run as a local service or a self-hosted web server (`placewise serve`, see
`docs/self-hosting.md`), with `placewise.Client` offering the identical interface.

## Geo toolkit (`placewise.geo`), no data needed

```python
from datetime import date
from placewise import geo

geo.distance(43.6532, -79.3832, 45.5019, -73.5674)                       # km, haversine
geo.distance(43.6532, -79.3832, 45.5019, -73.5674, method="geodesic")    # Karney, WGS84
geo.initial_bearing(43.65, -79.38, 45.50, -73.57)                        # degrees
geo.destination(43.65, -79.38, bearing=45, distance_km=10)
geo.parse("43°38′33.2″N 79°23′13.4″W")                                   # also Google/Apple/OSM URLs
geo.to_utm(43.6426, -79.3871)                                            # also UPS, MGRS, ECEF, ENU
geo.plus_code_encode(43.6426, -79.3871)
geo.sun_times(43.6426, -79.3871, date(2026, 6, 21))
```

Also: geohash, map tiles and quadkeys, encoded polylines, line simplification, nearest point on a
line, spherical areas, antimeridian-aware bounding boxes, a two-stage polygon index for detailed
GeoJSON or shapefile boundaries, and a registry of every coordinate system used with its EPSG code
(`placewise.constants.crs`).

## Tracks (`placewise.tracks`, `placewise.io`)

```python
from placewise.tracks import Track

track = Track.read("ride.fit")        # GPX, FIT, TCX, KML/KMZ, GeoJSON, NMEA or CSV, detected from content
track = track.clean()                 # sort, dedupe, drop invalid fixes, remove spikes, split gaps
track.stats()                         # distance, moving time, elevation gain, speeds, heart rate
track.position_at(photo_times)        # where you were at each time (great-circle interpolation)
track.stays()                         # places you stopped, with gap bridging
```

Readers and writers need no dependencies (FIT is decoded from the public spec). Operations include
Kalman smoothing, thinning, resampling, splits and best efforts, camera clock-offset estimation for
photo geotagging, trips, travel modes, flights, time inside an area, border crossings, days per
country, merging recordings from several devices, and route comparison (Hausdorff, Fréchet,
corridor overlap, deviations).

## Privacy (`placewise.privacy`)

```python
from placewise import privacy

key = b"..."                          # at least 16 secret bytes, kept and reused
shared = privacy.apply(track, privacy.preset("public_share"), key)
```

Privacy zones whose cut points don't give away the hidden place, secret-length trimming, keyed grid
snapping, geo-indistinguishable noise, time coarsening, and an audit of what a track reveals. Every
tool documents what it does *not* protect against.

## Data

```
placewise data install world          # download, verify and install a pack
placewise data list                   # installed and available packs (country packs: lookups
                                      # use them once installed)
placewise data update                 # newer versions (never automatic, never deletes)
placewise attribution                 # the installed packs' sources, licences and credits (--all, --short)
```

Everything placewise downloads lives in `~/.placewise/` unless configured otherwise (`--data-dir`,
`PLACEWISE_DATA_DIR` or `data.data_dir` in `placewise.toml`; `placewise data where` prints it).
Packs are memory-mapped and checksummed (format: `docs/pack-format.md`). Data sources are listed in
`src/placewise/sources/`, one JSON file per purpose (boundaries, places, regions, postal codes,
airports ...) giving the sources used in each region, and `ATTRIBUTION.md` is generated from them,
so an app that ships placewise data can link to that one file.

Packs are published as release assets of `amolvenkataraman/placewise-data` (`index.json` plus one
`.tar.xz` per pack); any copy of a release's files works as a mirror (`--index-url`, `data.mirrors`).

## Conventions

- Coordinates are WGS84 degrees, always in `(lat, lon)` order (GeoJSON uses `(lon, lat)`).
- Every function accepts scalars or numpy arrays and broadcasts; scalars in, plain floats out.
- Distances are kilometres unless a name ends in `_m`.
- English names only; standard coordinate systems only (no obfuscated ones like GCJ-02).

## Licence

The code is licensed under the [Apache License 2.0](LICENSE) (see also [NOTICE](NOTICE)). The data
packs keep their sources' licences (`ATTRIBUTION.md`); placewise's own curated datasets, in the
placewise-data repository, are CC BY 4.0.

## Disclaimer

placewise and its data packs are provided "as is" and "where is", with no warranty of any kind and
no legal liability for their use. Names, boundaries and other data may be wrong or out of date and
are not an official determination of any territory's status. See [DISCLAIMER.md](DISCLAIMER.md).

## Development

```
uv sync                 # creates .venv with the dev tools
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

Requires Python 3.10+. The runtime depends on numpy only; `pip install placewise[geodesic]` adds
GeographicLib for ellipsoidal distances. `packbuild/` (not shipped) turns public datasets into packs.
