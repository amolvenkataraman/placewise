"""PIN code areas -> LGD units: each PIN area's district, sub-district and urban local body (ULB).

PIN areas are delivery zones and cross administrative lines, so every answer is the unit that
holds most of the area by a proxy, and the derived layers are postal approximations:

- district and sub-district (`districts`), first rule that answers:
  1. "villages": the district (then sub-district) most of the PIN code's LGD villages are in;
  2. "indiapost": the India Post directory's district for the PIN code, matched by name (and
     the curated former names, `names`) to an LGD district of the same state;
  3. "ulb": the district most of the PIN areas of its ULB (LGD's ULB -> PIN table) are in;
  4. "neighbours": the district sharing the longest border with it, repeated until nothing
     changes (urban PIN areas with no villages and no directory match; islands get nothing).
- ULB (`ulbs`): a PIN area is a member of a ULB when it is urban (at most URBAN_PIN_KM2) and
  1. "seed": the curated dataset names it for a city whose LGD PIN table is empty or wrong;
  2. "lgd": LGD's pincode_urban lists it for that ULB (and for at most MAX_ULBS_PER_PIN ULBs:
     some rows give one office's PIN code for every ULB of a state), in the same state; several
     ULBs: the one with most member areas, then the higher type (corporation first);
  3. "neighbours": it isn't rural, has no ULB and shares the longest border with a member of
     a ULB of its state whose listed areas share its PIN block (then its district), repeated
     until nothing changes (Gurugram's unlisted PIN codes). Rural:
     LGD lists villages for it and India Post runs a branch office (B.O) there; branch offices
     are rural, while LGD lists revenue villages in city PIN areas too (Mumbai Suburban,
     Ahmedabad);
  4. "enclosed": it is rural but one ULB holds ENCLOSED_SHARE of its border (villages a city
     has grown round).
  A town whose only PIN area is big has no outline (the engine names it from GeoNames).
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from placewise.geo.shapes import area

from ..polygons import signed_area

# a PIN area at most this big (km2) can be part of a city; median urban PIN area ~ 5 km2,
# rural ones ~ 130 km2 (2026.11 build)
URBAN_PIN_KM2 = 40.0
# LGD rows that list one PIN code for more ULBs than this are an office address, not membership
MAX_ULBS_PER_PIN = 3
# an urban-sized PIN area with villages joins the ULB that holds this share of its border
ENCLOSED_SHARE = 0.75
# the first digits of a PIN code that India Post gives one city's offices as a block (Mumbai 4000xx
# and 4001xx, Thane 4006xx, Navi Mumbai 4007xx)
PIN_BLOCK = 4
# ULB types by rank when two claim one PIN area (LGD type names, as tidied by lgd._type_name)
ULB_TYPE_RANK = ("Municipal Corporation", "City Corporation", "Municipal Council", "City Municipal Council")


def folded(name):
    """A name for matching: upper case, letters and digits only ("Bengaluru Urban" = "BENGALURU URBAN")."""
    name = (name or "").upper().replace("&", " AND ")
    return re.sub(r"[^A-Z0-9]+", "", name)


def adjacency(features):
    """{(i, j): shared border length} for features (lists of (n, 2) rings) that share edges with
    identical vertices (India Post's areas do), i < j. Lengths are in degrees (for ranking)."""
    owner, a, b = [], [], []
    for i, rings in enumerate(features):
        for r in rings:
            if len(r) < 2:
                continue
            owner.append(np.full(len(r), i, dtype=np.int64))
            a.append(r)
            b.append(np.roll(r, -1, axis=0))
    if not owner:
        return {}
    owner, a, b = np.concatenate(owner), np.vstack(a), np.vstack(b)
    vertices, index = np.unique(np.vstack([a, b]), axis=0, return_inverse=True)
    index = index.ravel()
    u, v = index[: len(a)], index[len(a) :]
    lo, hi = np.minimum(u, v), np.maximum(u, v)
    key = lo.astype(np.int64) * len(vertices) + hi
    order = np.argsort(key, kind="stable")
    key, owner_sorted = key[order], owner[order]
    length = np.hypot(*(a[order] - b[order]).T)
    same = np.flatnonzero(key[1:] == key[:-1])
    out = defaultdict(float)
    for k in same.tolist():
        i, j = int(owner_sorted[k]), int(owner_sorted[k + 1])
        if i != j:
            out[min(i, j), max(i, j)] += float(length[k])
    return dict(out)


def _neighbours(adj, n):
    nb = [dict() for _ in range(n)]
    for (i, j), w in adj.items():
        nb[i][j] = nb[i].get(j, 0.0) + w
        nb[j][i] = nb[j].get(i, 0.0) + w
    return nb


def _spread(values, how, nb, eligible, label, same=None):
    """Fill values[i] == "" for eligible i from the neighbour with the longest shared border,
    until nothing changes; `same(i, value)` may veto a value."""
    changed = True
    while changed:
        changed = False
        updates = {}
        for i in np.flatnonzero(eligible).tolist():
            if values[i]:
                continue
            weight = Counter()
            for j, w in nb[i].items():
                if values[j] and (same is None or same(i, values[j])):
                    weight[values[j]] += w
            if weight:
                updates[i] = max(weight, key=lambda v, weight=weight: (weight[v], v))
        for i, v in updates.items():
            values[i], how[i] = v, label
            changed = True


def districts(pins, directory, indiapost, aliases, adj):
    """(district codes, sub-district codes, rules), one per PIN code in `pins`. `indiapost` gives
    (directory district name, ISO state code) per PIN; `aliases` maps (ISO state, folded name) to
    an LGD district code (former names from the curated dataset)."""
    n = len(pins)
    district, sub, how = [""] * n, [""] * n, [""] * n
    by_name = {(d.iso, folded(d.name)): code for code, d in directory.districts.items()}
    by_name.update(aliases)
    for i, pin in enumerate(pins):
        villages = directory.pin_villages.get(pin)
        if villages:
            per = Counter()
            for (d, _), count in villages.items():
                per[d] += count
            district[i] = max(per, key=lambda d, per=per: (per[d], d))
            subs = Counter({s: c for (d, s), c in villages.items() if d == district[i]})
            sub[i] = max(subs, key=lambda s, subs=subs: (subs[s], s))
            how[i] = "villages"
            continue
        name, iso = indiapost[i]
        code = by_name.get((iso, folded(name)))
        if code:
            district[i], how[i] = code, "indiapost"
    # 3. a ULB's district: the one most of its other areas are in
    index = {pin: i for i, pin in enumerate(pins)}
    ulb_district = {}
    per_ulb = defaultdict(Counter)
    for pin, ulbs in directory.pin_ulbs.items():
        i = index.get(pin)
        if i is not None and district[i]:
            for u in ulbs:
                per_ulb[u][district[i]] += 1
    for u, c in per_ulb.items():
        ulb_district[u] = max(c, key=lambda d, c=c: (c[d], d))
    for i, pin in enumerate(pins):
        if not district[i]:
            found = Counter(ulb_district[u] for u in directory.pin_ulbs.get(pin, ()) if u in ulb_district)
            if found:
                district[i], how[i] = max(found, key=lambda d, found=found: (found[d], d)), "ulb"
    nb = _neighbours(adj, n)
    _spread(district, how, nb, np.ones(n, dtype=bool), "neighbours")
    sub_how = [""] * n
    _spread(sub, sub_how, nb, np.ones(n, dtype=bool), "neighbours",
            same=lambda i, s: directory.subdistricts.get(s) is not None
            and directory.subdistricts[s].parent == district[i])  # fmt: skip
    return district, sub, how


def ulbs(
    pins,
    directory,
    state_of,
    area_km2,
    adj,
    seeds=None,
    perimeter=None,
    seed_states=None,
    branch_offices=None,
    district_of=None,
):
    """(ULB code or "", rule) per PIN code. `state_of[i]` is the PIN area's LGD state code (from
    its district), `area_km2[i]` its area, `seeds` {pin: ULB code} from the curated dataset,
    `seed_states` {ULB code: LGD state code} for seeded cities LGD no longer lists (BBMP) and
    `branch_offices` {pin: number of India Post branch offices} (None: every PIN code with
    villages counts as rural) and `district_of[i]` the PIN area's LGD district: unlisted areas
    join a neighbouring city with listed areas in their own PIN block first (Mulund, 400080 in
    Mumbai Suburban, joins Mumbai, listed for 4000xx, not neighbouring Thane; Kochi's 6820xx
    areas don't join Aluva, 6831xx, of the same district), then one with listed areas in their
    district; never a city with neither."""
    n = len(pins)
    ulb_state = {code: u.state for code, u in directory.ulbs.items()} | dict(seed_states or {})
    urban = np.asarray(area_km2, dtype=np.float64) <= URBAN_PIN_KM2
    ulb, how = [""] * n, [""] * n
    for i, pin in enumerate(pins):
        code = (seeds or {}).get(pin)
        if code:
            ulb[i], how[i] = code, "seed"
    claims = {}
    members = Counter()
    for i, pin in enumerate(pins):
        listed = directory.pin_ulbs.get(pin, set())
        if ulb[i] or not urban[i] or not listed or len(listed) > MAX_ULBS_PER_PIN:
            continue
        ok = sorted(u for u in listed if directory.ulbs[u].state == state_of[i])
        if ok:
            claims[i] = ok
            members.update(ok)
    for i, ok in claims.items():
        ulb[i] = min(ok, key=lambda u: (-members[u], _rank(directory.ulbs[u].kind), u))
        how[i] = "lgd"
    bo = branch_offices
    rural = np.array([bool(directory.pin_villages.get(p)) and (bo is None or bo.get(p, 0) > 0) for p in pins])
    nb = _neighbours(adj, n)
    same_state = lambda i, u: ulb_state.get(u) == state_of[i]  # noqa: E731
    blocks, districts_of = defaultdict(set), defaultdict(set)  # from each city's listed areas
    for i, u in enumerate(ulb):
        if u:
            blocks[u].add(pins[i][:PIN_BLOCK])
            if district_of is not None:
                districts_of[u].add(district_of[i])
    in_block = lambda i, u: same_state(i, u) and pins[i][:PIN_BLOCK] in blocks[u]  # noqa: E731
    _spread(ulb, how, nb, urban & ~rural, "neighbours", same=in_block)
    if district_of is not None:
        in_district = lambda i, u: same_state(i, u) and district_of[i] in districts_of[u]  # noqa: E731
        _spread(ulb, how, nb, urban & ~rural, "neighbours", same=in_district)
    if perimeter is not None:
        _enclosed(ulb, how, nb, urban & rural, perimeter, same_state)
    return ulb, how


def _enclosed(ulb, how, nb, eligible, perimeter, same):
    """Urban-sized areas with villages that one ULB surrounds (ENCLOSED_SHARE of their border)
    join it: villages a city has grown round (Bengaluru, Gurugram)."""
    changed = True
    while changed:
        changed = False
        for i in np.flatnonzero(eligible).tolist():
            if ulb[i] or not perimeter[i]:
                continue
            weight = Counter()
            for j, w in nb[i].items():
                if ulb[j] and same(i, ulb[j]):
                    weight[ulb[j]] += w
            if weight:
                best = max(weight, key=lambda v, weight=weight: (weight[v], v))
                if weight[best] >= ENCLOSED_SHARE * perimeter[i]:
                    ulb[i], how[i] = best, "enclosed"
                    changed = True


def areas_km2(features):
    """Each feature's area on the sphere (km2): shells minus holes, for features as lists of (n, 2)
    lon/lat rings wound as regions_layer.feature_rings winds them (shells clockwise)."""
    out = np.zeros(len(features))
    for i, rings in enumerate(features):
        for r in rings:
            a = area([r[:, ::-1]])
            out[i] += a if signed_area(r) < 0 else -a
    return out


def perimeters(features):
    """Each feature's total ring length (degrees, as adjacency measures it)."""
    return np.array(
        [sum(float(np.hypot(*(r - np.roll(r, -1, axis=0)).T).sum()) for r in rings) for rings in features]
    )


def _rank(kind):
    return ULB_TYPE_RANK.index(kind) if kind in ULB_TYPE_RANK else len(ULB_TYPE_RANK)


@dataclass(frozen=True)
class Crosswalk:
    """Per PIN code (in the pincodes layer's order): LGD district, sub-district and city codes
    and the rule that gave each; `city` is the curated city a ULB belongs to (Delhi's three
    former corporations are one city), else the ULB itself."""

    district: list
    subdistrict: list
    district_rule: list
    city: list
    city_rule: list
    state: list  # LGD state code, from the district


def build(pins, rings, indiapost, directory, names, branch_offices=None):
    """The Crosswalk for PIN areas `pins` with `rings` (per PIN, its (n, 2) lon/lat rings, wound
    as regions_layer.feature_rings winds them), `indiapost` (directory district name, ISO state)
    per PIN, the LGD `directory`, the curated `names` (packbuild.ind.names.Names) and the
    directory's branch offices per PIN code (ulbs)."""
    adj = adjacency(rings)
    district, sub, how = districts(pins, directory, indiapost, names.district_aliases(directory), adj)
    state = [directory.districts[d].state if d else "" for d in district]
    seeds, seed_states, merged = {}, {}, {}
    state_of_iso = {s.iso: code for code, s in directory.states.items()}
    for c in names.cities:
        code = c["id"].rpartition(":")[2]
        for member in c["lgd"]:
            merged[member] = code
        for pin in c.get("pincodes") or ():
            seeds[pin] = code
        seed_states[code] = state_of_iso.get(f"IN-{c['state']}", "")
    ulb, ulb_how = ulbs(
        pins, directory, state, areas_km2(rings), adj, seeds, perimeters(rings), seed_states, branch_offices,
        district,
    )  # fmt: skip
    city = [merged.get(u, u) for u in ulb]
    return Crosswalk(district, sub, how, city, ulb_how, state)
