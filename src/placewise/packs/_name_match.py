"""Matching machinery behind NameIndex: sorted key tables searched by bisection, the id lookup,
and the fuzzy trigram index with its bounded edit distance."""

import bisect
import math

import numpy as np

from placewise.constants import names as nc


class KeyTable:
    """A sorted table of distinct UTF-8 keys (`<prefix>_keys.bin` + `.idx.npy`) and each key's
    slice of the entry arrays (`<prefix>_start.npy`). Indexing gives a key's bytes, so the
    standard bisect module searches it; UTF-8 byte order is code point order."""

    def __init__(self, path, prefix):
        self.blob = (path / f"{prefix}_keys.bin").read_bytes()
        self.offsets = np.load(path / f"{prefix}_keys.idx.npy", allow_pickle=False).astype(np.int64)
        self.start = np.load(path / f"{prefix}_start.npy", allow_pickle=False).astype(np.int64)
        self._offsets = self.offsets.tolist()  # plain ints index fastest during bisection

    def __len__(self):
        return len(self._offsets) - 1

    def __getitem__(self, k):
        return self.blob[self._offsets[k] : self._offsets[k + 1]]

    def find(self, text):
        """Index of the key equal to `text`, or -1."""
        q = text.encode("utf-8")
        k = bisect.bisect_left(self, q)
        return k if k < len(self) and self[k] == q else -1

    def prefix_range(self, text):
        """[lo, hi) of the keys starting with `text` (0xFF never occurs in UTF-8)."""
        q = text.encode("utf-8")
        return bisect.bisect_left(self, q), bisect.bisect_left(self, q + b"\xff")

    def entries(self, lo, hi):
        """The entry range [start, stop) of keys lo..hi-1."""
        return int(self.start[lo]), int(self.start[hi])

    def entry_lengths(self, entry):
        """Byte length of each entry's key."""
        k = np.searchsorted(self.start, entry, side="right") - 1
        return self.offsets[k + 1] - self.offsets[k]

    def decode_all(self):
        """Every key as one str and each key's length in characters."""
        text = self.blob.decode("utf-8")
        starts = np.frombuffer(self.blob, dtype=np.uint8) & 0xC0 != 0x80  # first byte of a character
        chars = np.concatenate([[0], np.cumsum(starts)])[self.offsets]
        return text, np.diff(chars)


class IdView:
    """A layer's ids in sorted order (`names/ids/<layer>.npy`), for bisection by id."""

    def __init__(self, layer, order):
        self.layer, self.order = layer, order
        self.codes = layer._array("col/id.npy")

    def __len__(self):
        return len(self.order)

    def __getitem__(self, i):
        return self.layer._string(int(self.codes[self.order[i]]))


class Trigrams:
    """Postings from each padded character trigram (" to", "tor", ... "to ") to the keys holding
    it, built in memory from a KeyTable: a few hundred ms for a couple of hundred thousand keys."""

    def __init__(self, codes, start, postings, sizes, lengths):
        self.codes, self.start, self.postings = codes, start, postings
        self.sizes, self.lengths = sizes, lengths  # distinct trigrams and characters per key

    @classmethod
    def build(cls, table):
        if not len(table):
            empty = np.zeros(0, dtype=np.int64)
            return cls(empty.astype(np.uint64), np.zeros(1, np.int64), empty, empty, empty)
        text, lengths = table.decode_all()
        chars = np.frombuffer(text.encode("utf-32-le"), dtype=np.uint32).astype(np.uint64)
        owner = np.repeat(np.arange(len(lengths)), lengths)
        padded = np.full(len(chars) + 2 * len(lengths), ord(" "), dtype=np.uint64)
        padded[np.arange(len(chars)) + 2 * owner + 1] = chars
        at = np.arange(len(chars)) + 2 * owner  # key i's j-th trigram starts at its j-th character
        codes = _trigram_codes(padded, at)
        order = np.argsort(codes, kind="stable")  # stable: keys stay ascending within a trigram
        codes, owner = codes[order], owner[order]
        keep = np.r_[True, (codes[1:] != codes[:-1]) | (owner[1:] != owner[:-1])]
        codes, owner = codes[keep], owner[keep].astype(np.int32)
        distinct, first = np.unique(codes, return_index=True)
        start = np.append(first, len(codes)).astype(np.int64)
        sizes = np.bincount(owner, minlength=len(lengths))
        return cls(distinct, start, owner, sizes, lengths)

    def near(self, q, table):
        """(keys, match_score) of the keys within the edit bound of `q`, unordered."""
        padded = np.array([ord(" "), *map(ord, q), ord(" ")], dtype=np.uint64)
        mine = np.unique(_trigram_codes(padded, np.arange(len(q))))
        at = np.searchsorted(self.codes, mine)
        at = at[(at < len(self.codes)) & (self.codes[np.minimum(at, len(self.codes) - 1)] == mine)]
        if not len(at):
            return np.zeros(0, np.int64), np.zeros(0)
        hits = self.postings[ranges(self.start[at], self.start[at + 1])]
        keys, shared = np.unique(hits, return_counts=True)
        need = max(1, math.ceil(nc.FUZZY_MIN_SHARED * len(mine)))
        lengths = self.lengths[keys]
        bound = (nc.FUZZY_MAX_EDIT_RATIO * np.maximum(lengths, len(q))).astype(np.int64)
        ok = (shared >= need) & (np.abs(lengths - len(q)) <= bound)
        keys, shared = keys[ok], shared[ok]
        jaccard = shared / (len(mine) + self.sizes[keys] - shared)
        if len(keys) > nc.FUZZY_EDIT_POOL:
            best = np.argpartition(-jaccard, nc.FUZZY_EDIT_POOL)[: nc.FUZZY_EDIT_POOL]
            keys = keys[best]
        out_keys, out_score = [], []
        for k in keys.tolist():
            other = table[k].decode("utf-8")
            longer = max(len(q), len(other))
            limit = int(nc.FUZZY_MAX_EDIT_RATIO * longer)
            edits = edit_distance(q, other, limit)
            if edits <= limit:
                out_keys.append(k)
                out_score.append(1 - edits / longer)
        return np.array(out_keys, dtype=np.int64), np.array(out_score)


def _trigram_codes(padded, at):
    """21 bits per code point, three code points per trigram."""
    return (padded[at] << np.uint64(42)) | (padded[at + 1] << np.uint64(21)) | padded[at + 2]


def edit_distance(a, b, limit):
    """Damerau-Levenshtein distance (optimal string alignment: adjacent transpositions count as one
    edit) between a and b, or limit + 1 once it must exceed `limit`."""
    if a == b:
        return 0
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    before, prev = None, list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        low = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                v = min(v, before[j - 2] + 1)
            cur[j] = v
            low = min(low, v)
        if low > limit:
            return limit + 1
        before, prev = prev, cur
    return prev[-1] if prev[-1] <= limit else limit + 1


def ranges(start, stop):
    """The ranges start[i]:stop[i], concatenated into one index array."""
    start, stop = np.asarray(start, dtype=np.int64), np.asarray(stop, dtype=np.int64)
    sizes = stop - start
    total = int(sizes.sum())
    if not total:
        return np.zeros(0, dtype=np.int64)
    shift = start - np.concatenate([[0], np.cumsum(sizes)[:-1]])
    return np.arange(total, dtype=np.int64) + np.repeat(shift, sizes)
