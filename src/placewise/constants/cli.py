"""The `placewise` command line (placewise.cli)."""

# `placewise lookup --csv`: the coordinate columns read by default, the answer columns added (in
# this order, after the input's own) and how many rows are looked up at once
LOOKUP_LAT_COLUMN = "lat"
LOOKUP_LON_COLUMN = "lon"
LOOKUP_CSV_COLUMNS = ("label", "locality", "city", "admin1", "country", "postal", "tz", "within", "water")
LOOKUP_BATCH = 10_000
BAD_ROWS_SHOWN = 10  # row numbers listed in the warning about rows without valid coordinates
