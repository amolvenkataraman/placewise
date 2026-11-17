"""LGD reports in their exact CSV format for the India fixtures (india_fixtures: PIN areas round
MG Road, the Gateway of India, the Charminar, India Gate and Leh), written at test time.

Codes are LGD's real state codes; district, sub-district, village and ULB codes are LGD's real
ones for those public places where known, otherwise made up. Villages are made up.
"""

import csv

STATES_HEADER = (
    "S.No.", "State Code", "State Version", "State Name (In English)", "State Name (In Local)",
    "Census 2001 Code", "Census 2011 Code", "State or UT",
)  # fmt: skip
DISTRICTS_HEADER = (
    "S.No.", "State Code", "State Name (In English)", "District Code", "District Name(In English)",
    "Census 2001 Code", "Census 2011 Code",
)  # fmt: skip
SUBDISTRICTS_HEADER = (
    "S.No.", "State Code", "State Name", "District Code", "District Name", "Sub-district Code",
    "Sub-district Version", "Sub-district Name", "Census 2001 Code", "Census 2011 Code",
)  # fmt: skip
ULBS_HEADER = (
    "S.No.", "State Code", "State Name", "Local Body Code", "Local Body Version",
    "Local Body Name (In English)", "Local Body Name (In Local)", "Localbody Type Code", "Census 2011 Code",
)  # fmt: skip
PIN_VILLAGES_HEADER = (
    "S.No.", "State Code", "State Name", "District Code", "District Name", "SubDistrict Code",
    "SubDistrict Name", "Village Code", "Village Name", "Pincode",
)  # fmt: skip
PIN_URBAN_HEADER = (
    "S.No.", "State Code", "State Name", "Localbody Code", "Localbody Name", "Localbody Type Name", "Pincode",
)  # fmt: skip

STATES = [
    ("29", "Karnataka", "S"), ("27", "Maharashtra", "S"), ("36", "Telangana", "S"), ("7", "Delhi", "U"),
    ("37", "Ladakh", "U"),
]  # fmt: skip
DISTRICTS = [
    ("29", "Karnataka", "572", "Bengaluru Urban"),
    ("27", "Maharashtra", "482", "Mumbai"),
    ("36", "Telangana", "536", "Hyderabad"),
    ("7", "Delhi", "77", "New Delhi"),
    ("37", "Ladakh", "39", "Leh Ladakh"),
]
SUBDISTRICTS = [
    ("29", "572", "5587", "Bengaluru North"),
    ("27", "482", "4136", "Mumbai City"),
    ("36", "536", "4618", "Charminar"),
    ("7", "77", "6005", "Chanakya Puri"),
    ("37", "39", "6201", "Leh"),
]
ULBS = [
    # state, code, name, local name, type code, census 2011
    ("29", "305851", "Bengaluru Central City Corporation(Gba)", "Bengaluru Central City Corporation(Gba)",
     "4", "0"),
    ("27", "251488", "Greater Mumbai", "मोठे मुंबई", "4", "802794"),
    ("36", "251664", "Hyderabad", "హైదరాబాద్", "4", "802918"),
    ("7", "276447", "New Delhi Municipal Council", "नई दिल्ली नगरपालिका परिषद", "21", "0"),
    ("37", "248151", "Leh", "Leh", "5", "800004"),
]  # fmt: skip
# (district, sub-district, village code, village name, pincode)
VILLAGES = [
    ("39", "6201", "900001", "Choglamsar", "194101"),
    ("39", "6201", "900002", "Stok", "194101"),
    ("536", "4618", "900003", "Synthetic Village", "500002"),
]
# (ULB, type name, pincode): Leh's PIN area is big and rural, so it is no member of the town
PIN_URBAN = [
    ("251488", "Municipal Corporation", "400001"),
    ("251664", "Municipal Corporation", "500002"),
    ("276447", "NCT Municipal Council", "110001"),
    ("248151", "Municipality", "194101"),
]


def _write(path, header, rows):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows((i + 1, *r) for i, r in enumerate(rows))
    return path


def write_lgd(folder, pin_urban=None, villages=None):
    """{table: path} of the six LGD reports in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    state_name = {s[0]: s[1] for s in STATES}
    district_name = {d[2]: d[3] for d in DISTRICTS}
    sub_name = {s[2]: s[3] for s in SUBDISTRICTS}
    ulb = {u[1]: u for u in ULBS}
    return {
        "states": _write(
            folder / "states.csv", STATES_HEADER,
            [(c, 1, n, n.upper(), c, c, k) for c, n, k in STATES],
        ),
        "districts": _write(
            folder / "districts.csv", DISTRICTS_HEADER, [(s, sn, c, n, "0", "0") for s, sn, c, n in DISTRICTS]
        ),
        "subdistricts": _write(
            folder / "subdistricts.csv", SUBDISTRICTS_HEADER,
            [(s, state_name[s], d, district_name[d], c, 1, n, "0", "0") for s, d, c, n in SUBDISTRICTS],
        ),
        "urban_local_bodies": _write(
            folder / "urban_local_bodies.csv", ULBS_HEADER,
            [(s, state_name[s], c, 3, n, local, t, census) for s, c, n, local, t, census in ULBS],
        ),
        "pincode_villages": _write(
            folder / "pincode_villages.csv", PIN_VILLAGES_HEADER,
            [
                ("37" if d == "39" else "36", "x", d, district_name[d], s, sub_name[s], v, vn, pin)
                for d, s, v, vn, pin in (VILLAGES if villages is None else villages)
            ],
        ),
        "pincode_urban": _write(
            folder / "pincode_urban.csv", PIN_URBAN_HEADER,
            [
                (ulb[c][0], state_name[ulb[c][0]], c, ulb[c][2], t, pin)
                for c, t, pin in (PIN_URBAN if pin_urban is None else pin_urban)
            ],
        ),
    }  # fmt: skip
