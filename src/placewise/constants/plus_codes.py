"""Open Location Code (plus codes), from the official specification:
https://github.com/google/open-location-code/blob/main/Documentation/Specification/specification.md
"""

# base 20, chosen so codes can't spell words and few symbols are easy to confuse
ALPHABET = "23456789CFGHJMPQRVWX"
BASE = len(ALPHABET)
SEPARATOR = "+"
SEPARATOR_POSITION = 8  # digits before the separator in a full code
PADDING = "0"

MIN_DIGITS = 2
MAX_DIGITS = 15
# the first 10 digits are lat/lon pairs in base 20; the rest each pick a cell of a 5 x 4 grid
PAIR_DIGITS = 10
GRID_ROWS = 5
GRID_COLUMNS = 4
DEFAULT_LENGTH = 10  # about 14 x 14 m

# a 15-digit code's cell in integer units per degree: 20**3 * 5**5 and 20**3 * 4**5. Encoding in
# integers rather than repeatedly dividing floats is what keeps every implementation in agreement.
LAT_UNITS_PER_DEGREE = BASE**3 * GRID_ROWS ** (MAX_DIGITS - PAIR_DIGITS)
LON_UNITS_PER_DEGREE = BASE**3 * GRID_COLUMNS ** (MAX_DIGITS - PAIR_DIGITS)

# cell sizes in degrees of the pair digits, by number of pairs (2, 4, 6, 8, 10 digits)
PAIR_RESOLUTIONS = (20.0, 1.0, 0.05, 0.0025, 0.000125)
# shortening keeps the reference within this fraction of the cell left implied; the spec allows
# up to 0.5 but the reference implementations and their test data use 0.3 so a code still
# recovers when a different geocoder puts the reference place slightly elsewhere
SHORTEN_SAFETY = 0.3
MIN_SHORTENABLE_LENGTH = 6
