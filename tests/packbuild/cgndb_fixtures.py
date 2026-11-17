# ruff: noqa: E501  (rows copied from the real file are longer than a line)
"""A CGNDB national CSV cut to a few populated places (and rows the layer drops), for the Canada
pack tests: rows copied from cgn_canada_csv_eng.csv, Source shortened, three invented railway,
post office and borough rows."""

import zipfile
from pathlib import Path

HEADER = (
    "﻿CGNDB ID,Geographical Name,ISO Language Code,Language,Syllabic Form,Generic Term,Generic Category,"
    "Concise Code,Toponymic Feature ID,Latitude,Longitude,Location,Province - Territory,Relevance at Scale,"
    "Decision Date,Source\n"
)
# rows copied from cgn_canada_csv_eng.csv (Source shortened)
ROWS = """\
IACFT,Lake Louise,und,Undetermined,,Hamlet,Populated Place,UNP,0cff7e46,51.4252778,-116.1805556,28-28-16-W5,Alberta,1200000,1952-04-03,AB
JAVJO,Field,und,Undetermined,,Community,Populated Place,UNP,d1c6039f,51.3955556,-116.4880556,Kootenay Land District,British Columbia,2000000,1983-03-31,BC
FDQBU,Scarborough,und,Undetermined,,Community,Populated Place,UNP,50bee57b,43.7558333,-79.2308334,York,Ontario,1200000,1998-01-01,ON
FEBVQ,Malton,und,Undetermined,,Urban Community,Populated Place,UNP,3c9ca166,43.7034500,-79.6476700,Peel,Ontario,145000,1968-01-01,ON
FAAAA,Malton,und,Undetermined,,Railway Point,Populated Place,UNP,aaaa0001,43.7000000,-79.6400000,Peel,Ontario,50000,1968-01-01,ON
FBBBB,Malton,und,Undetermined,,Post Office,Populated Place,UNP,aaaa0002,43.7010000,-79.6410000,Peel,Ontario,50000,1968-01-01,ON
JCBNA,101 Mile Lake,und,Undetermined,,Lake,Water Feature,LAKE,0ca65836,51.6675000,-121.2936110,Lillooet,British Columbia,250000,1966-03-10,BC
EDLAA,Ville-Marie,fra,French,,Borough,Populated Place,UNP,bbbb0001,45.5088000,-73.5540000,Montréal,Quebec,85000,2002-01-01,QC
"""


def write_archive(folder):
    """cgn_canada_csv_eng.zip in `folder`, as NRCan ships it."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    csv_path = folder / "cgn_canada_csv_eng.csv"
    csv_path.write_text(HEADER + ROWS, encoding="utf-8")
    path = folder / "cgn_canada_csv_eng.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.write(csv_path, csv_path.name)
    return path
