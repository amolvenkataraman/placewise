"""Matching machinery behind NameIndex: sorted key tables searched by bisection, the id lookup,
and the fuzzy trigram index (built in memory, or read from the pack where the writer stored it
packed) with its bounded edit distance."""

import bisect
import math
import threading

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
        return decode_keys(self.blob, self.offsets)

    def lengths(self):
        """Each key's length in characters."""
        return _char_lengths(self.blob, self.offsets)


def decode_keys(blob, offsets):
    """(every key as one str, each key's length in characters) of a key blob and its offsets."""
    return blob.decode("utf-8"), _char_lengths(blob, offsets)


def _char_lengths(blob, offsets):
    """Each key's bytes less its UTF-8 continuation bytes (found once: they are rare)."""
    offsets = np.asarray(offsets, dtype=np.int64)
    more = np.flatnonzero((np.frombuffer(blob, dtype=np.uint8) & 0xC0) == 0x80)
    owner = np.searchsorted(offsets, more, side="right") - 1
    return np.diff(offsets) - np.bincount(owner, minlength=len(offsets) - 1)


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
    it (ascending key numbers), built in memory from a KeyTable: a few hundred ms for a couple of
    hundred thousand keys. PackedTrigrams reads the same postings from the pack instead."""

    def __init__(self, codes, start, postings, sizes, lengths):
        self.codes, self.start, self.postings = codes, start, postings
        self.sizes, self.lengths = sizes, lengths  # distinct trigrams and characters per key
        self.counts = np.diff(start)  # postings per trigram

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
        if not len(self.codes):
            return np.zeros(0, np.int64), np.zeros(0)
        padded = np.array([ord(" "), *map(ord, q), ord(" ")], dtype=np.uint64)
        mine = np.unique(_trigram_codes(padded, np.arange(len(q))))
        at = np.searchsorted(self.codes, mine)
        at = at[(at < len(self.codes)) & (self.codes[np.minimum(at, len(self.codes) - 1)] == mine)]
        if not len(at):
            return np.zeros(0, np.int64), np.zeros(0)
        need = max(1, math.ceil(nc.FUZZY_MIN_SHARED * len(mine)))
        if len(at) < need:
            return np.zeros(0, np.int64), np.zeros(0)
        keys, shared = self._shared(at, need)
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

    def _shared(self, at, need):
        """(keys, shared) for every key holding at least `need` of the trigrams `at`, with how
        many it holds. A key holding `need` of them holds one of the rarest len(at) - need + 1, so
        only their postings are gathered; the commoner trigrams' postings (sorted) are only
        searched for those candidates."""
        at = at[np.argsort(self.counts[at], kind="stable")]
        rare, common = at[: len(at) - need + 1], at[len(at) - need + 1 :]
        keys, shared = np.unique(self.gather(rare), return_counts=True)
        for t in common.tolist():
            posting = self.posting(t)
            i = np.minimum(np.searchsorted(posting, keys), len(posting) - 1)
            shared += posting[i] == keys
        return keys, shared

    def gather(self, at):
        """The postings of trigrams `at`, concatenated."""
        return self.postings[ranges(self.start[at], self.start[at + 1])]

    def posting(self, t):
        """The keys holding trigram `t`, ascending."""
        return self.postings[self.start[t] : self.start[t + 1]]

    def packed(self):
        """{file: contents} of the postings as PackedTrigrams reads them (docs/pack-format.md)."""
        delta = self.postings.astype(np.int64)
        delta[1:] -= delta[:-1].copy()
        firsts = self.start[:-1][self.counts > 0]
        delta[firsts] = self.postings[firsts]  # each posting starts from its first key itself
        blob, ends = _varint(delta)
        byte_start = np.concatenate([[0], ends])[self.start]
        repeats = np.flatnonzero(self.sizes != self.lengths)
        return {
            nc.TRIGRAM_CODES: self.codes.astype(np.uint64),
            nc.TRIGRAM_START: byte_start.astype(np.uint32 if byte_start[-1] < 2**32 else np.int64),
            nc.TRIGRAM_COUNTS: self.counts.astype(np.int32),
            nc.TRIGRAM_REPEATS: np.stack([repeats, self.sizes[repeats]], axis=1).astype(np.int32),
            nc.TRIGRAM_POSTINGS: blob,
        }


class PackedTrigrams(Trigrams):
    """The trigram postings as the pack writer stored them in names/ (docs/pack-format.md):
    memory-mapped, each posting's ascending key numbers delta- and varint-encoded, decoded when a
    lookup reads it. A key's distinct trigram count is its length, except for the few keys
    listed with a repeated trigram ("banana")."""

    def __init__(self, path, table):
        def load(name):  # a plain ndarray over the mapped file: indexing it skips memmap's overhead
            return np.asarray(np.load(path / name, mmap_mode="r", allow_pickle=False))

        self.codes, self.start, self.counts = (
            load(nc.TRIGRAM_CODES),
            load(nc.TRIGRAM_START),
            load(nc.TRIGRAM_COUNTS),
        )
        repeats = load(nc.TRIGRAM_REPEATS)
        blob = path / nc.TRIGRAM_POSTINGS
        empty = not blob.stat().st_size  # numpy can't map an empty file
        self.blob = np.zeros(0, np.uint8) if empty else np.asarray(np.memmap(blob, dtype=np.uint8, mode="r"))
        self.lengths = table.lengths()
        self.sizes = self.lengths.copy()
        self.sizes[repeats[:, 0]] = repeats[:, 1]
        self._decoded, self._kept, self._lock = {}, 0, threading.Lock()  # posting() keeps big ones

    @classmethod
    def present(cls, path):
        return (path / nc.TRIGRAM_CODES).is_file()

    def gather(self, at):
        at = np.asarray(at, dtype=np.int64)
        delta = _unvarint(self.blob[ranges(self.start[at], self.start[at + 1])])
        counts = self.counts[at].astype(np.int64)
        total = np.cumsum(delta)
        before = np.concatenate([[0], total])[np.cumsum(counts) - counts]  # restart each posting
        return total - np.repeat(before, counts)

    def posting(self, t):
        """Decoded once and kept while it is among the last few big ones read: a common trigram
        ("an ") is read by many queries, and decoding it costs more than finding it."""
        found = self._decoded.get(t)
        if found is not None:
            return found
        found = np.cumsum(_unvarint(self.blob[int(self.start[t]) : int(self.start[t + 1])]))
        if len(found) >= nc.TRIGRAM_KEEP_MIN:
            found.flags.writeable = False  # shared by every later caller
            with self._lock:
                self._decoded[t] = found
                self._kept += len(found)
                while self._kept > nc.TRIGRAM_KEEP_TOTAL:
                    self._kept -= len(self._decoded.pop(next(iter(self._decoded))))
        return found


def _varint(values):
    """(bytes, end of each value): non-negative ints, 7 bits per byte, low bits first, the high
    bit set on every byte but a value's last."""
    values = np.asarray(values, dtype=np.int64)
    size = np.ones(len(values), dtype=np.int64)
    for k in range(1, 9):
        size += values >= 1 << (7 * k)
    ends = np.cumsum(size)
    out = np.empty(int(ends[-1]) if len(ends) else 0, dtype=np.uint8)
    first = ends - size
    for k in range(int(size.max()) if len(size) else 0):
        has = np.flatnonzero(size > k)
        more = (size[has] > k + 1).astype(np.int64) << 7
        out[first[has] + k] = ((values[has] >> (7 * k)) & 0x7F) | more
    return out.tobytes(), ends


def _unvarint(data):
    """The values _varint encoded into `data` (a uint8 array of whole values)."""
    if not len(data):
        return np.zeros(0, dtype=np.int64)
    last = data < 0x80
    if last.all():
        return data.astype(np.int64)
    ends = np.flatnonzero(last)
    starts = np.concatenate([[0], ends[:-1] + 1])
    shift = 7 * (np.arange(len(data)) - np.repeat(starts, ends - starts + 1))
    return np.add.reduceat((data & 0x7F).astype(np.int64) << shift, starts)


def _trigram_codes(padded, at):
    """21 bits per code point, three code points per trigram."""
    return (padded[at] << np.uint64(42)) | (padded[at + 1] << np.uint64(21)) | padded[at + 2]


def edit_distance(a, b, limit):
    """Damerau-Levenshtein distance (optimal string alignment: adjacent transpositions count as one
    edit) between a and b, or limit + 1 once it must exceed `limit`. Only the diagonal band
    |i - j| <= limit is filled: cells outside it are above the limit anyway."""
    if a == b:
        return 0
    n, m = len(a), len(b)
    if abs(n - m) > limit:
        return limit + 1
    big = limit + 1
    before, prev = None, [j if j <= limit else big for j in range(m + 1)]
    for i in range(1, n + 1):
        ca = a[i - 1]
        cur = [big] * (m + 1)
        if i <= limit:
            cur[0] = i
        low = cur[0]
        for j in range(max(1, i - limit), min(m, i + limit) + 1):
            cb = b[j - 1]
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                v = min(v, before[j - 2] + 1)
            cur[j] = v
            if v < low:
                low = v
        if low > limit:
            return big
        before, prev = prev, cur
    return prev[m] if prev[m] <= limit else big


def ranges(start, stop):
    """The ranges start[i]:stop[i], concatenated into one index array."""
    start, stop = np.asarray(start, dtype=np.int64), np.asarray(stop, dtype=np.int64)
    sizes = stop - start
    total = int(sizes.sum())
    if not total:
        return np.zeros(0, dtype=np.int64)
    shift = start - np.concatenate([[0], np.cumsum(sizes)[:-1]])
    return np.arange(total, dtype=np.int64) + np.repeat(shift, sizes)
