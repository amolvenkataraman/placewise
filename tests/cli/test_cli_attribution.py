"""`placewise attribution`: the installed packs' sources by default, `--all` for the whole registry,
`--short` for one credit line per source. Synthetic packs written straight into the data dir."""

import json

import numpy as np
import pytest

from placewise import attribution
from placewise.cli import main
from placewise.packs import LayerData, write_pack


def _install(data_dir, name, version, sources):
    layer = LayerData(
        name="spots",
        kind="point",
        columns={"id": [f"synthetic:{name}:0"], "name": ["Spot"]},
        sources=tuple(sources),
        lat=np.array([10.0]),
        lon=np.array([30.0]),
    )
    return write_pack(data_dir / "packs", name, version, [layer], created="2026-11-17T00:00:00Z")


@pytest.fixture
def run(capsys, data_dir):
    def _run(*argv):
        code = main(["--data-dir", str(data_dir), "attribution", *argv])
        out, err = capsys.readouterr()
        return code, out, err

    return _run


@pytest.fixture
def installed(data_dir):
    _install(data_dir, "world", "2026.10", ["ourairports"])  # older version: not read
    _install(data_dir, "world", "2026.11", ["naturalearth", "geonames"])
    _install(data_dir, "usa", "2026.11", ["uscensus", "geonames"])
    return ["naturalearth", "geonames", "uscensus"]


def test_lists_only_the_installed_packs_sources(run, installed):
    code, out, err = run()
    assert (code, err) == (0, "")
    assert out == attribution.render_markdown(only=installed, subject="the installed data packs")
    assert "## US Census" in out and "## GeoNames" in out and "Statistics Canada" not in out
    assert "OurAirports" not in out  # only in a version that isn't the current one


def test_all_lists_the_whole_registry(run, installed):
    assert run("--all") == (0, attribution.render_markdown(), "")


def test_short_is_one_credit_line_per_source(run, installed):
    sources = attribution.load_sources()
    code, out, _ = run("--short")
    assert code == 0 and out.splitlines() == [sources[i].credit for i in sources if i in installed]
    code, out, _ = run("--short", "--all")
    assert code == 0 and out.splitlines() == [s.credit for s in sources.values()]


def test_json_follows_the_same_choice(run, installed):
    code, out, _ = run("--json")
    assert code == 0 and set(json.loads(out)) == set(installed)
    code, out, _ = run("--json", "--all")
    assert code == 0 and set(json.loads(out)) == set(attribution.load_sources())
    assert json.loads(out)["geonames"] == attribution.source("geonames").to_dict()


def test_short_and_json_together_are_refused(run, installed):
    code, out, err = run("--short", "--json")
    assert code == 2 and out == "" and "not allowed with" in err


def test_without_installed_packs_it_says_how_to_list_everything(run):
    code, out, err = run()
    assert code == 1 and out == ""
    assert "no packs installed" in err and "--all" in err


def test_a_source_missing_from_the_registry_is_named_not_fatal(run, data_dir):
    _install(data_dir, "world", "2026.11", ["naturalearth", "someone-elses-source"])
    code, out, err = run("--short")
    assert code == 0 and out == attribution.source("naturalearth").credit + "\n"
    assert "someone-elses-source" in err
