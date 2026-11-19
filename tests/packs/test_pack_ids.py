"""Derived ids (docs/pack-format.md, "Derived ids"): a layer may leave its `id` column out and
let readers build each id from a template over its other columns. Synthetic codes only."""

import dataclasses
import json

import numpy as np
import pytest
from pack_kit import CREATED, point_layer

from placewise.packs import IdTemplate, NameData, open_pack, write_pack

# (country, code, place): codes repeat (a code's other places), some with spaces or hyphens
ROWS = (
    ("AA", "100 01", "Alpha"),
    ("AA", "100-02", "Beta"),
    ("AA", "100 01", "Gamma"),  # the code's second point
    ("BB", "100 01", "Delta"),  # the same code, another country
    ("AA", "100 03", "Epsilon"),
    ("AA", "100 01", "Zeta"),  # third
    ("BB", "200", "Eta"),
)
TEMPLATE = IdTemplate("test:{country}:{name:compact}", repeat=":{n}")


def _ids(rows=ROWS):
    count, out = {}, []
    for country, code, _ in rows:
        count[country, code] = count.get((country, code), 0) + 1
        base = f"test:{country}:{code.replace(' ', '').replace('-', '')}"
        out.append(base if count[country, code] == 1 else f"{base}:{count[country, code]}")
    return out


def _layer(ids=None, template=TEMPLATE, rows=ROWS):
    n = len(rows)
    layer = point_layer(
        np.linspace(10, 20, n),
        np.linspace(30, 40, n),
        name="codes",
        country=[r[0] for r in rows],
        place=[r[2] for r in rows],
        reach=np.arange(n, dtype=np.int32),
    )
    layer.columns["id"] = list(ids or _ids(rows))
    layer.columns["name"] = [r[1] for r in rows]
    return dataclasses.replace(layer, id_template=template)


def _names(n):
    return NameData.from_rows([(f"Place {i}", "codes", i, "postal_code", 0.5, "official") for i in range(n)])


def _write(tmp_path, layer, name="ids", names=False):
    index = _names(len(layer.columns["id"])) if names else None
    return open_pack(write_pack(tmp_path, name, "2026.11", [layer], created=CREATED, names=index))


def _meta(pack, layer="codes"):
    return json.loads((pack.path / layer / "layer.json").read_text())


def test_ids_matching_the_template_are_not_stored(tmp_path):
    pack = _write(tmp_path, _layer())
    spec = _meta(pack)["fields"]["id"]
    assert spec == {"type": "str", "template": TEMPLATE.text, "repeat": ":{n}", "exceptions": 0}
    assert not (pack.path / "codes" / "col" / "id.npy").exists()
    assert not any("id." in f for f in pack.manifest["files"])
    blob = (pack.path / "codes" / "strings.bin").read_bytes()
    assert b"test:" not in blob  # no id string in the string table


def test_derived_ids_read_exactly_as_stored_ones(tmp_path):
    derived = _write(tmp_path, _layer(), "derived")["codes"]
    stored = _write(tmp_path, _layer(template=None), "stored")["codes"]
    assert (stored.path / "col" / "id.npy").exists()
    assert derived.fields == stored.fields
    want = _ids()
    assert derived.column("id").tolist() == stored.column("id").tolist() == want
    assert [derived.value("id", i) for i in range(len(ROWS))] == want
    assert derived.value("id", -1) == want[-1]
    assert [derived.row(i) for i in range(len(ROWS))] == [stored.row(i) for i in range(len(ROWS))]
    for i, ident in enumerate(want):
        assert derived.find("id", ident).tolist() == [i]
    assert derived.find("id", "test:AA:nope").tolist() == []
    values, inverse = derived.distinct("id")
    s_values, s_inverse = stored.distinct("id")
    assert values.tolist() == s_values.tolist() and inverse.tolist() == s_inverse.tolist()


def test_repeats_count_rows_in_order_by_the_raw_values(tmp_path):
    ids = _write(tmp_path, _layer())["codes"].column("id").tolist()
    assert ids[0] == "test:AA:10001"
    assert ids[2] == "test:AA:10001:2"
    assert ids[5] == "test:AA:10001:3"
    assert ids[3] == "test:BB:10001"  # another country: its own count
    assert ids[1] == "test:AA:10002"  # compact drops hyphens as well as spaces


def test_rows_that_differ_from_the_template_are_stored_as_exceptions(tmp_path):
    ids = _ids()
    ids[1], ids[6] = "test:AA:10002#special", "elsewhere:7"
    pack = _write(tmp_path, _layer(ids))
    assert _meta(pack)["fields"]["id"]["exceptions"] == 2
    col = pack.path / "codes" / "col"
    assert np.load(col / "id.except_rows.npy").tolist() == [1, 6]
    layer = pack["codes"]
    assert layer.column("id").tolist() == ids
    assert [layer.value("id", i) for i in range(len(ids))] == ids
    assert layer.find("id", "elsewhere:7").tolist() == [6]


def test_a_template_that_fits_too_few_rows_is_not_used(tmp_path):
    ids = [f"other:{i}" for i in range(len(ROWS))]
    pack = _write(tmp_path, _layer(ids))
    assert _meta(pack)["fields"]["id"] == {"type": "str"}
    assert pack["codes"].column("id").tolist() == ids


def test_tail_takes_the_text_after_the_last_colon(tmp_path):
    rows = (("AA", "1", "a"), ("BB", "2", "b"))
    layer = _layer(["t:AA:x", "t:BB:y"], IdTemplate("t:{country}:{place:tail}"), rows)
    layer.columns["place"] = ["src:x", "src:y"]
    pack = _write(tmp_path, layer)
    assert _meta(pack)["fields"]["id"]["exceptions"] == 0
    assert pack["codes"].column("id").tolist() == ["t:AA:x", "t:BB:y"]


def test_a_template_without_fields_numbers_the_rows(tmp_path):
    n = len(ROWS)
    ids = ["row"] + [f"row{i}" for i in range(2, n + 1)]
    pack = _write(tmp_path, _layer(ids, IdTemplate("row", repeat="{n}")))
    assert _meta(pack)["fields"]["id"]["exceptions"] == 0
    layer = pack["codes"]
    assert layer.column("id").tolist() == ids
    assert layer.value("id", 3) == "row4"


@pytest.mark.parametrize(
    ("template", "message"),
    [
        (IdTemplate("x:{nope}"), "no str field 'nope'"),
        (IdTemplate("x:{reach}"), "no str field 'reach'"),
        (IdTemplate("x:{id}"), "no str field 'id'"),
        (IdTemplate("x:{name:upper}"), "unknown transform 'upper'"),
        (IdTemplate("x:{name"), "unbalanced"),
        (IdTemplate("x:name}"), "unbalanced"),
        (IdTemplate("x:{name}", repeat=":2"), "repeat"),
        (IdTemplate("x:{name}", repeat=":{n}{n}"), "repeat"),
    ],
)
def test_bad_templates_are_refused(tmp_path, template, message):
    with pytest.raises(ValueError, match=message):
        _write(tmp_path, _layer(template=template))


def test_ids_are_still_checked_before_the_template(tmp_path):
    ids = _ids()
    ids[1] = ids[0]
    with pytest.raises(ValueError, match="unique"):
        _write(tmp_path, _layer(ids))


def test_get_by_id_through_the_name_index(tmp_path):
    ids = _ids()
    ids[4] = "test:AA:special"
    pack = _write(tmp_path, _layer(ids), names=True)
    plain = _write(tmp_path, _layer(ids, template=None), "plain", names=True)
    files = sorted(f for f in pack.manifest["files"] if f.startswith("names/"))
    assert files == sorted(f for f in plain.manifest["files"] if f.startswith("names/"))
    for f in files:  # the name index is the same, ids order included
        assert (pack.path / f).read_bytes() == (plain.path / f).read_bytes()
    for i, ident in enumerate(ids):
        found = pack.names.codes(ident)
        assert found.row.tolist() == [i], ident
        assert pack.names.codes(ident).entry.tolist() == plain.names.codes(ident).entry.tolist()
    assert len(pack.names.codes("test:AA:10001:9")) == 0


@pytest.mark.parametrize("high", [5, 2**40])  # one combined sort key, or too big for one
def test_occurrences_count_earlier_rows_with_the_same_values(high):
    from placewise.packs._ids import occurrences

    rng = np.random.default_rng(3)
    a, b = rng.integers(0, 5, 2000) * (high // 5), rng.integers(0, 4, 2000)
    seen, want = {}, []
    for key in zip(a.tolist(), b.tolist(), strict=True):
        seen[key] = seen.get(key, 0) + 1
        want.append(seen[key])
    assert occurrences([a, b], 2000).tolist() == want
    assert occurrences([], 3).tolist() == [1, 2, 3]
    assert occurrences([np.zeros(0, np.int64)], 0).tolist() == []
