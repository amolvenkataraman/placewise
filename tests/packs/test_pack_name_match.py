import random

import numpy as np

from placewise.packs._name_match import Trigrams, edit_distance, ranges


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
