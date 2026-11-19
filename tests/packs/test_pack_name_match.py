import random

import numpy as np

from placewise.packs._names.match import Trigrams, edit_distance, ranges


def _reference(a, b):
    """Optimal string alignment distance, the full table."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def test_edit_distance_counts_transpositions_as_one():
    assert edit_distance("toronto", "toronto", 2) == 0
    assert edit_distance("torono", "toronto", 2) == 1
    assert edit_distance("sprinfgield", "springfield", 2) == 1
    assert edit_distance("abc", "xyz", 1) == 2  # past the limit: limit + 1


def test_banded_edit_distance_matches_the_full_table():
    rng = random.Random(7)
    for _ in range(3000):
        a = "".join(rng.choice("abc ") for _ in range(rng.randint(0, 9)))
        b = "".join(rng.choice("abc ") for _ in range(rng.randint(0, 9)))
        limit = rng.randint(0, 5)
        assert edit_distance(a, b, limit) == min(_reference(a, b), limit + 1), (a, b, limit)


class _Table:
    def __init__(self, keys):
        self.keys = sorted(keys)
        self.blob = "".join(self.keys).encode()
        sizes = [len(k.encode()) for k in self.keys]
        self.offsets = np.concatenate([[0], np.cumsum(sizes)]).astype(np.int64)

    def __len__(self):
        return len(self.keys)

    def __getitem__(self, k):
        return self.keys[k].encode()

    def decode_all(self):
        return "".join(self.keys), np.array([len(k) for k in self.keys])


def test_shared_trigram_counts_match_a_full_count():
    rng = random.Random(3)
    keys = {"".join(rng.choice("abcd") for _ in range(rng.randint(2, 8))) for _ in range(400)}
    trigrams = Trigrams.build(_Table(keys))
    for _ in range(50):
        at = np.unique(rng.choices(range(len(trigrams.codes)), k=rng.randint(1, 8)))
        need = rng.randint(1, len(at))
        hits = trigrams.postings[ranges(trigrams.start[at], trigrams.start[at + 1])]
        every, count = np.unique(hits, return_counts=True)
        keys_found, shared = trigrams._shared(at, need)
        expected = count >= need
        got = shared >= need
        assert set(every[expected].tolist()) == set(keys_found[got].tolist())
        assert dict(zip(keys_found[got].tolist(), shared[got].tolist(), strict=True)) == dict(
            zip(every[expected].tolist(), count[expected].tolist(), strict=True)
        )


def test_varint_round_trips_every_size():
    from placewise.packs._names.match import _unvarint, _varint

    rng = np.random.default_rng(5)
    values = np.concatenate([[0, 1, 127, 128, 16383, 16384, 2**31 - 1, 2**40], rng.integers(0, 2**24, 500)])
    blob, ends = _varint(values)
    assert len(blob) == ends[-1] and ends[0] == 1 and ends[2] - ends[1] == 1 and ends[3] - ends[2] == 2
    assert _unvarint(np.frombuffer(blob, dtype=np.uint8)).tolist() == values.tolist()
    assert _unvarint(np.zeros(0, dtype=np.uint8)).tolist() == []


def _write_packed(trigrams, path):
    for name, contents in trigrams.packed().items():
        if isinstance(contents, bytes):
            (path / name).write_bytes(contents)
        else:
            np.save(path / name, contents)


class _LengthTable(_Table):
    def lengths(self):
        return self.decode_all()[1]


def test_packed_trigrams_read_back_the_same_postings_and_answers(tmp_path):
    from placewise.packs._names.match import PackedTrigrams

    rng = random.Random(11)
    words = ["toronto", "banana", "bananarama", "mississauga", "zürich", "東京", "a", "aaaa"]
    keys = set(words) | {
        "".join(rng.choice("abcdeé ") for _ in range(rng.randint(1, 12))) for _ in range(3000)
    }
    table = _LengthTable(keys)
    built = Trigrams.build(table)
    _write_packed(built, tmp_path)
    assert PackedTrigrams.present(tmp_path)
    packed = PackedTrigrams(tmp_path, table)
    np.testing.assert_array_equal(packed.codes, built.codes)
    np.testing.assert_array_equal(packed.sizes, built.sizes)
    np.testing.assert_array_equal(packed.lengths, built.lengths)
    np.testing.assert_array_equal(packed.counts, built.counts)
    every = np.arange(len(built.codes))
    np.testing.assert_array_equal(packed.gather(every), built.postings)
    for t in rng.sample(range(len(built.codes)), 50):
        np.testing.assert_array_equal(packed.posting(t), built.posting(t))
    for q in [*words, "torono", "bannana", "misisauga", "zurich", "abcde", "e", "xyz"]:
        a, b = built.near(q, table), packed.near(q, table)
        assert a[0].tolist() == b[0].tolist() and a[1].tolist() == b[1].tolist(), q


def test_an_empty_trigram_index_packs_and_reads_back(tmp_path):
    from placewise.packs._names.match import PackedTrigrams

    table = _LengthTable([])
    _write_packed(Trigrams.build(table), tmp_path)
    packed = PackedTrigrams(tmp_path, table)
    assert len(packed.codes) == 0 and packed.near("toronto", table)[0].tolist() == []


def test_packed_trigrams_keep_only_a_bounded_set_of_big_decoded_postings(tmp_path, monkeypatch):
    from placewise.constants import names as nc
    from placewise.packs._names.match import PackedTrigrams

    rng = random.Random(2)
    table = _LengthTable({"".join(rng.choice("ab") for _ in range(rng.randint(3, 10))) for _ in range(600)})
    built = Trigrams.build(table)
    _write_packed(built, tmp_path)
    monkeypatch.setattr(nc, "TRIGRAM_KEEP_MIN", 50)
    monkeypatch.setattr(nc, "TRIGRAM_KEEP_TOTAL", 400)
    packed = PackedTrigrams(tmp_path, table)
    for _ in range(2):
        for t in range(len(built.codes)):
            np.testing.assert_array_equal(packed.posting(t), built.posting(t))
            assert packed._kept == sum(len(p) for p in packed._decoded.values()) <= 400
            assert all(len(p) >= 50 for p in packed._decoded.values())
    assert packed._decoded
