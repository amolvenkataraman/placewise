"""Garmin FIT protocol and profile values: the file header, base types, and the messages and fields
placewise reads. Numbers, scales and offsets are those of the public FIT SDK profile (Profile.xlsx);
a decoded value is `raw / scale - offset`."""

from typing import NamedTuple

# 1989-12-31T00:00:00Z, the zero of every FIT date_time
EPOCH_UNIX_S = 631065600

# date_time values below this count seconds since the device powered on, not since the epoch
MIN_ABSOLUTE_TIME = 0x10000000

# positions are signed 32-bit semicircles: 2**31 of them make 180 degrees
SEMICIRCLES_TO_DEGREES = 180 / 2**31

HEADER_SIZES = (12, 14)  # the 14-byte header adds a CRC of the first 12 bytes
HEADER_SIGNATURE = b".FIT"
CRC_SIZE = 2


class BaseType(NamedTuple):
    name: str
    code: str  # struct format character
    size: int  # bytes
    invalid: int | None  # the raw value meaning "no data"; None where it is NaN or an empty string


# Keyed by base type number, the low five bits of the base type byte (the top bit only flags
# multi-byte types, so readers should not rely on it)
BASE_TYPES = {
    0x00: BaseType("enum", "B", 1, 0xFF),
    0x01: BaseType("sint8", "b", 1, 0x7F),
    0x02: BaseType("uint8", "B", 1, 0xFF),
    0x03: BaseType("sint16", "h", 2, 0x7FFF),
    0x04: BaseType("uint16", "H", 2, 0xFFFF),
    0x05: BaseType("sint32", "i", 4, 0x7FFFFFFF),
    0x06: BaseType("uint32", "I", 4, 0xFFFFFFFF),
    0x07: BaseType("string", "s", 1, None),  # UTF-8, NUL-terminated or padded
    0x08: BaseType("float32", "f", 4, None),
    0x09: BaseType("float64", "d", 8, None),
    0x0A: BaseType("uint8z", "B", 1, 0),
    0x0B: BaseType("uint16z", "H", 2, 0),
    0x0C: BaseType("uint32z", "I", 4, 0),
    0x0D: BaseType("byte", "s", 1, None),
    0x0E: BaseType("sint64", "q", 8, 0x7FFFFFFFFFFFFFFF),
    0x0F: BaseType("uint64", "Q", 8, 0xFFFFFFFFFFFFFFFF),
    0x10: BaseType("uint64z", "Q", 8, 0),
}
BASE_TYPE_NUMBER_MASK = 0x1F

# Record header bits
HEADER_COMPRESSED = 0x80  # compressed-timestamp header: local type in bits 5-6, time offset in 0-4
HEADER_DEFINITION = 0x40
HEADER_DEVELOPER = 0x20  # on a definition: developer field definitions follow
LOCAL_MESSAGE_MASK = 0x0F
COMPRESSED_LOCAL_SHIFT, COMPRESSED_LOCAL_MASK = 5, 0x03
COMPRESSED_OFFSET_MASK = 0x1F  # the offset is the low five bits of the timestamp

# Global message numbers
MESG_FILE_ID = 0
MESG_SESSION = 18
MESG_LAP = 19
MESG_RECORD = 20
MESG_EVENT = 21
MESG_DEVICE_INFO = 23

FIELD_TIMESTAMP = 253  # the same number in every message


class Field(NamedTuple):
    name: str
    scale: float = 1
    offset: float = 0
    kind: str | None = None  # "time" (date_time), "semicircles", "string" or None for a number


_TIME = Field("timestamp", kind="time")

MESSAGE_FIELDS = {
    MESG_FILE_ID: {
        0: Field("type"),
        1: Field("manufacturer"),
        2: Field("product"),
        3: Field("serial_number"),
        4: Field("time_created", kind="time"),
        8: Field("product_name", kind="string"),
    },
    MESG_RECORD: {
        FIELD_TIMESTAMP: _TIME,
        0: Field("position_lat", kind="semicircles"),
        1: Field("position_long", kind="semicircles"),
        2: Field("altitude", 5, 500),
        3: Field("heart_rate"),
        4: Field("cadence"),
        5: Field("distance", 100),
        6: Field("speed", 1000),
        7: Field("power"),
        13: Field("temperature"),
        31: Field("gps_accuracy"),
        73: Field("enhanced_speed", 1000),
        78: Field("enhanced_altitude", 5, 500),
    },
    MESG_LAP: {
        FIELD_TIMESTAMP: _TIME,
        2: Field("start_time", kind="time"),
        7: Field("total_elapsed_time", 1000),
        8: Field("total_timer_time", 1000),
        9: Field("total_distance", 100),
        25: Field("sport"),
    },
    MESG_SESSION: {
        FIELD_TIMESTAMP: _TIME,
        2: Field("start_time", kind="time"),
        5: Field("sport"),
        7: Field("total_elapsed_time", 1000),
        8: Field("total_timer_time", 1000),
        9: Field("total_distance", 100),
    },
    MESG_EVENT: {
        FIELD_TIMESTAMP: _TIME,
        0: Field("event"),
        1: Field("event_type"),
    },
    MESG_DEVICE_INFO: {
        FIELD_TIMESTAMP: _TIME,
        0: Field("device_index"),
        2: Field("manufacturer"),
        3: Field("serial_number"),
        4: Field("product"),
        5: Field("software_version", 100),
        27: Field("product_name", kind="string"),
    },
}

# event / event_type values that bound continuous recording
EVENT_TIMER = 0
EVENT_TYPE_START = 0
EVENT_TYPES_STOP = frozenset({1, 4, 8, 9})  # stop, stop_all, stop_disable, stop_disable_all

FILE_TYPES = {
    1: "device",
    2: "settings",
    3: "sport",
    4: "activity",
    5: "workout",
    6: "course",
    7: "schedules",
    9: "weight",
    10: "totals",
    11: "goals",
    14: "blood_pressure",
    15: "monitoring_a",
    20: "activity_summary",
    28: "monitoring_daily",
    32: "monitoring_b",
    34: "segment",
    35: "segment_list",
}

SPORTS = {
    0: "generic",
    1: "running",
    2: "cycling",
    3: "transition",
    4: "fitness_equipment",
    5: "swimming",
    6: "basketball",
    7: "soccer",
    8: "tennis",
    9: "american_football",
    10: "training",
    11: "walking",
    12: "cross_country_skiing",
    13: "alpine_skiing",
    14: "snowboarding",
    15: "rowing",
    16: "mountaineering",
    17: "hiking",
    18: "multisport",
    19: "paddling",
    20: "flying",
    21: "e_biking",
    22: "motorcycling",
    23: "boating",
    24: "driving",
    25: "golf",
    26: "hang_gliding",
    27: "horseback_riding",
    28: "hunting",
    29: "fishing",
    30: "inline_skating",
    31: "rock_climbing",
    32: "sailing",
    33: "ice_skating",
    34: "sky_diving",
    35: "snowshoeing",
    36: "snowmobiling",
    37: "stand_up_paddleboarding",
    38: "surfing",
    39: "wakeboarding",
    40: "water_skiing",
    41: "kayaking",
    42: "rafting",
    43: "windsurfing",
    44: "kitesurfing",
    45: "tactical",
    46: "jumpmaster",
    47: "boxing",
    48: "floor_climbing",
    49: "baseball",
    53: "diving",
    62: "hiit",
    64: "racket",
    65: "wheelchair_push_walk",
    66: "wheelchair_push_run",
    67: "meditation",
    69: "disc_golf",
    71: "cricket",
    72: "rugby",
    73: "hockey",
    74: "lacrosse",
    75: "volleyball",
    76: "water_tubing",
    77: "wakesurfing",
    80: "mixed_martial_arts",
    82: "snorkeling",
    83: "dance",
    84: "jump_rope",
}

# The makers whose files are common; others are reported by number
MANUFACTURERS = {
    1: "garmin",
    15: "dynastream",
    23: "suunto",
    32: "wahoo_fitness",
    38: "osynce",
    41: "shimano",
    63: "specialized",
    68: "cateye",
    69: "stages_cycling",
    70: "sigmasport",
    71: "tomtom",
    86: "elite",
    89: "tacx",
    95: "stryd",
    255: "development",
    260: "zwift",
    265: "strava",
    294: "coros",
}
