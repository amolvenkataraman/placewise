"""UTM, UPS and MGRS on WGS84: grid parameters, letter tables, and the Krüger series for the
transverse Mercator (Karney 2011, "Transverse Mercator with an accuracy of a few nanometers")."""

from .wgs84 import A_M, F

# --- UTM ---
UTM_K0 = 0.9996  # central-meridian scale factor
UTM_FALSE_EASTING_M = 500_000.0
UTM_FALSE_NORTHING_SOUTH_M = 10_000_000.0  # southern hemisphere only, so northings stay positive
UTM_ZONE_WIDTH_DEG = 6.0
# UTM is defined on [-80, 84); beyond that UPS takes over
UTM_MIN_LAT = -80.0
UTM_MAX_LAT = 84.0

# --- UPS ---
UPS_K0 = 0.994  # scale at the pole
UPS_FALSE_EASTING_M = 2_000_000.0
UPS_FALSE_NORTHING_M = 2_000_000.0

# --- MGRS ---
MGRS_SQUARE_M = 100_000.0
# 8-degree latitude bands from 80S; X is stretched to 12 degrees so it reaches 84N
MGRS_BANDS = "CDEFGHJKLMNPQRSTUVWX"
MGRS_BAND_HEIGHT_DEG = 8.0
# 100 km column letters repeat every three zones; I and O are never used
MGRS_UTM_COLUMNS = ("ABCDEFGH", "JKLMNPQR", "STUVWXYZ")  # zone % 3 == 1, 2, 0
MGRS_UTM_ROWS = "ABCDEFGHJKLMNPQRSTUV"  # repeats every 2000 km of northing
MGRS_UTM_EVEN_ZONE_ROW_SHIFT = 5  # even zones start their rows at F, to keep neighbours distinct
# polar bands: west/east of the meridian through the pole; (letters, first square in 100 km units)
MGRS_UPS_COLUMNS = {
    "A": ("JKLPQRSTUXYZ", 8),
    "B": ("ABCFGHJKLPQR", 20),
    "Y": ("RSTUXYZ", 13),
    "Z": ("ABCFGHJ", 20),
}
MGRS_UPS_ROWS = {
    "A": ("ABCDEFGHJKLMNPQRSTUVWXYZ", 8),
    "B": ("ABCDEFGHJKLMNPQRSTUVWXYZ", 8),
    "Y": ("ABCDEFGHJKLMNP", 13),
    "Z": ("ABCDEFGHJKLMNP", 13),
}
MGRS_MAX_DIGITS = 11  # per axis, as GeographicLib reads them (5 for 1 m, the rest sub-metre)

# --- Krüger series, to order n^6 (Karney 2011, eqs. 14, 35, 36) ---
N = F / (2 - F)  # third flattening
_n2, _n3, _n4, _n5, _n6 = N**2, N**3, N**4, N**5, N**6
# radius of the rectifying sphere: 2*pi*A is the meridian's length
RECTIFYING_RADIUS_M = A_M / (1 + N) * (1 + _n2 / 4 + _n4 / 64 + _n6 / 256)
KRUGER_ALPHA = (  # geographic -> transverse Mercator
    N / 2 - 2 * _n2 / 3 + 5 * _n3 / 16 + 41 * _n4 / 180 - 127 * _n5 / 288 + 7891 * _n6 / 37800,
    13 * _n2 / 48 - 3 * _n3 / 5 + 557 * _n4 / 1440 + 281 * _n5 / 630 - 1983433 * _n6 / 1935360,
    61 * _n3 / 240 - 103 * _n4 / 140 + 15061 * _n5 / 26880 + 167603 * _n6 / 181440,
    49561 * _n4 / 161280 - 179 * _n5 / 168 + 6601661 * _n6 / 7257600,
    34729 * _n5 / 80640 - 3418889 * _n6 / 1995840,
    212378941 * _n6 / 319334400,
)
KRUGER_BETA = (  # transverse Mercator -> geographic
    N / 2 - 2 * _n2 / 3 + 37 * _n3 / 96 - _n4 / 360 - 81 * _n5 / 512 + 96199 * _n6 / 604800,
    _n2 / 48 + _n3 / 15 - 437 * _n4 / 1440 + 46 * _n5 / 105 - 1118711 * _n6 / 3870720,
    17 * _n3 / 480 - 37 * _n4 / 840 - 209 * _n5 / 4480 + 5569 * _n6 / 90720,
    4397 * _n4 / 161280 - 11 * _n5 / 504 - 830251 * _n6 / 7257600,
    4583 * _n5 / 161280 - 108847 * _n6 / 3991680,
    20648693 * _n6 / 638668800,
)
