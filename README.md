# placewise

Offline, two-way geocoding and a geo toolkit. Given a point it answers the way a person would
(the city you'd say, the region, the park or lake you were in, the airport you were at); given a
name it returns where that is. Everything runs locally.

Status: early development. The first slice is the toolkit in `placewise.geo`, which needs no data.

```python
from placewise import geo

geo.distance(43.6532, -79.3832, 45.5019, -73.5674)  # km, haversine
geo.distance(43.6532, -79.3832, 45.5019, -73.5674, method="geodesic")
geo.initial_bearing(43.65, -79.38, 45.50, -73.57)  # degrees
geo.destination(43.65, -79.38, bearing=45, distance_km=10)
geo.bbox_around(43.65, -79.38, distance_km=25)
geo.parse("43°38′33.2″N 79°23′13.4″W")
geo.geohash_encode(43.65, -79.38)
```

Conventions:

- Coordinates are WGS84 degrees, always in `(lat, lon)` order (GeoJSON uses `(lon, lat)`).
- Every function accepts scalars or numpy arrays and broadcasts; scalars in, plain floats out.
- Distances are kilometres unless a function says otherwise.

## Development

```
uv sync                 # creates .venv with the dev tools
uv run pytest           # tests
uv run ruff check .     # lint
uv run ruff format .    # format
```

Requires Python 3.10+. The core depends on numpy only; `pip install placewise[geodesic]` adds
GeographicLib for ellipsoidal distances.
