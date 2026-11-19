"""`placewise lookup` through main(argv): the card, JSON, CSV batches, --packs and --worldview."""

import csv
import json

import pytest

from placewise.cli import main
from tests.search.search_kit import write_packs


@pytest.fixture(scope="module")
def packs(tmp_path_factory):
    out = tmp_path_factory.mktemp("lookup-packs")
    write_packs(out)  # world, alpha (towns, a national park, a lake), parkspots
    return out


def run(capsys, *argv):
    code = main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def test_lookup_prints_the_card(packs, capsys):
    code, out, err = run(capsys, "lookup", "0.75", "-139.5", "--packs", str(packs))
    assert code == 0 and err == ""
    lines = out.splitlines()
    assert lines[0].startswith("Alpha City") and lines[0].endswith("(0.75000, -139.50000)")
    assert any(line.split()[:3] == ["country", "Alphaland", "(XA)"] for line in lines)
    assert "\x1b[" not in out  # not a terminal: plain text
    assert max(map(len, lines)) <= 100


def test_lookup_accepts_lat_comma_lon_and_a_pack_list(packs, capsys):
    dirs = [str(p) for p in sorted(packs.iterdir())]
    code, out, _ = run(capsys, "lookup", "0.75,-139.5", "--packs", *dirs)
    assert code == 0 and out.startswith("Alpha City")


def test_lookup_json_and_worldview(packs, capsys):
    code, out, _ = run(capsys, "lookup", "0.35", "-139.8", "--json", "--packs", str(packs))
    data = json.loads(out)
    assert code == 0 and data["lat"] == 0.35 and data["country"]["codes"]["iso2"] == "XA"
    code, out, _ = run(
        capsys, "lookup", "0.75", "-139.5", "--json", "--worldview", "XB", "--packs", str(packs)
    )
    assert code == 0 and json.loads(out)["country"]["name"] == "Alphaland"


def test_lookup_usage_errors(packs, capsys):
    assert main(["lookup", "0.75", "--packs", str(packs)]) == 2  # a latitude without a longitude
    assert main(["lookup", "--packs", str(packs)]) == 2  # nothing to look up
    assert main(["lookup", "95", "0", "--packs", str(packs)]) == 1  # not a latitude
    assert "not a valid" in capsys.readouterr().err
    assert main(["lookup", "1", "2", "--packs", str(packs / "nope")]) == 1
    assert "no packs" in capsys.readouterr().err


def write_csv(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_csv_batch_writes_the_answer_columns(packs, tmp_path, capsys):
    src, dst = tmp_path / "in.csv", tmp_path / "out.csv"
    write_csv(src, ["name", "lat", "lon"], [["a", "0.75", "-139.5"], ["b", "0.35", "-139.8"], ["c", "", "x"]])
    code, out, err = run(capsys, "lookup", "--csv", str(src), "--out", str(dst), "--packs", str(packs))
    assert code == 0 and out == ""
    rows = read_csv(dst)
    answers = ["label", "locality", "city", "admin1", "country", "postal", "tz", "within", "water"]
    assert list(rows[0]) == ["name", "lat", "lon", *answers]
    assert (
        rows[0]["name"] == "a" and rows[0]["country"] == "Alphaland" and rows[0]["admin1"] == "North Province"
    )
    assert rows[0]["label"].startswith("Alpha City")
    assert rows[1]["label"] and rows[1]["country"] == "Alphaland"
    assert rows[2]["label"] == "" and rows[2]["name"] == "c"  # no coordinates: blank answer, row kept
    assert "1 row" in err and "row 3" in err


def test_csv_batch_column_names_and_stdout(packs, tmp_path, capsys):
    src = tmp_path / "in.csv"
    write_csv(src, ["Latitude", "Longitude"], [["0.75", "-139.5"]])
    code, out, _ = run(
        capsys, "lookup", "--csv", str(src), "--lat-column", "Latitude", "--lon-column", "Longitude",
        "--packs", str(packs),
    )  # fmt: skip
    assert code == 0
    rows = list(csv.DictReader(out.splitlines()))
    assert rows[0]["Latitude"] == "0.75" and rows[0]["country"] == "Alphaland"
    code, _, err = run(capsys, "lookup", "--csv", str(src), "--packs", str(packs))
    assert code == 1 and "no column 'lat'" in err


def test_altitude_reaches_the_lookup(packs, tmp_path, capsys, monkeypatch):
    from placewise.cli import _common

    seen, real = [], _common.open_geocoder

    class Spy:
        def __init__(self, geocoder):
            self.geocoder = geocoder

        def lookup(self, *args, **kwargs):
            seen.append(kwargs["altitude_m"])
            return self.geocoder.lookup(*args, **kwargs)

        def lookup_many(self, *args, **kwargs):
            seen.append(kwargs["altitude_m"])
            return self.geocoder.lookup_many(*args, **kwargs)

    monkeypatch.setattr(_common, "open_geocoder", lambda args: Spy(real(args)))
    assert main(["lookup", "0.75", "-139.5", "--altitude", "10000", "--packs", str(packs)]) == 0
    assert main(["lookup", "0.75", "-139.5", "--packs", str(packs)]) == 0
    src = tmp_path / "in.csv"
    write_csv(src, ["lat", "lon"], [["0.75", "-139.5"]])
    assert main(["lookup", "--csv", str(src), "--altitude", "-20.5", "--packs", str(packs)]) == 0
    assert seen == [10000.0, None, -20.5]
    capsys.readouterr()
