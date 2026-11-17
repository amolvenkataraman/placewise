"""NMEA 0183 position sentences (GGA, RMC, GLL): https://gpsd.gitlab.io/gpsd/NMEA.html"""

# GPS, multi-constellation, GLONASS, Galileo, BeiDou (BD before NMEA 4.11, GB from it)
TALKER_IDS = ("GP", "GN", "GL", "GA", "BD", "GB")
SENTENCES = ("GGA", "RMC", "GLL")
# GGA fix quality 0 is "no fix"; receivers still repeat their last position with it
NO_FIX_QUALITY = 0
# RMC and GLL status: A = valid, V = void
VALID_STATUS = "A"
# NMEA 2.3+ mode indicator N = data not valid, even when the status field says otherwise
INVALID_MODE = "N"
# RMC carries a two-digit year; GPS began in 1980, so 80-99 are 19xx and 00-79 are 20xx
CENTURY_PIVOT = 80
SECONDS_PER_DAY = 86400
# a time of day that jumps back by more than half a day means the UTC date turned over
ROLLOVER_JUMP_S = SECONDS_PER_DAY / 2
# user-equivalent range error turning HDOP into metres; ~5 m (1 sigma) is typical of single-frequency
# civil GPS, so HDOP x this is a rough horizontal accuracy, not a receiver-reported one
DEFAULT_UERE_M = 5.0
