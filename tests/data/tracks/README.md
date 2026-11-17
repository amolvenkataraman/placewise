# Real-world track fixtures

Short stretches of public-transit rides recorded at 1 Hz with a phone GPS logger, contributed by
the project owner as realistic test data (GPS jitter, speed, satellite counts, urban canyons,
highway driving). Licensed under CC BY 4.0: see `LICENSE.md`.

Anonymised before inclusion:

- every point within 2 km of a home, work, school or frequently visited place, and within 500 m of
  any other place the owner stayed at, was removed; only the longest remaining stretch was kept,
  and a further 300 m was trimmed from each end;
- long rides were cut to a ~30-minute middle stretch;
- timestamps were shifted to 1 January 2001 (intervals unchanged), so neither dates nor times of
  day are real;
- no device, app or account information is included.

| File | Route | Points | Distance | Duration |
|---|---|---|---|---|
| ttc_900_airport_express.gpx | TTC 900 Airport Express, Toronto | 725 | 10.4 km | 12 min |
| yrt_viva_purple.gpx | YRT Viva Purple, York Region | 600 | 4.9 km | 10 min |
| hyderabad_airport_express.gpx | Hyderabad airport express bus | 1,800 | 22.5 km | 30 min |
| hyderabad_bengaluru_highway.gpx | Hyderabad to Bengaluru coach, highway stretch | 1,800 | 37.5 km | 30 min |

Format: GPX 1.0 with `ele`, `time`, `speed` (m/s) and `sat` per point, as written by GPS loggers.
