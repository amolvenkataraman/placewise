# Worldviews

Where borders are disputed, which country a point is in depends on who you ask. placewise answers
**de facto** by default (who administers the ground) and lets the caller, or the operator, choose
another view. Nothing here is an official determination of any territory's status
([DISCLAIMER.md](../DISCLAIMER.md)).

```python
import placewise

r = placewise.lookup(35.9208, 74.3089, worldview="IN")   # Gilgit, in India's view
r.label                                                   # "Gilgit, Ladakh, India"
r.disputed.name, r.disputed.applied_view                  # "Gilgit-Baltistan", "IN"

placewise.lookup(22.2793, 114.1628).country.name          # "Hong Kong"
placewise.lookup(22.2793, 114.1628, worldview="CN").cc    # "CN"
```

## Orders

A worldview is an ordered list, read left to right per point (`WorldviewSettings.order`, the
`worldview=` argument, `?worldview=IN,de_facto` on the server):

- `de_facto`: the country polygon's own country;
- `disputed`: no country if the point is in a disputed area; otherwise the next entry;
- a view code (`IN`, `CN`, `US` ...; ISO alpha-3 such as `IND` works too): the country that view
  gives the point; if it gives none, the next entry.

If nothing decides, the point is answered de facto. A view the world pack has no data for warns
once (`UserWarning`) with the list of views it has, and is skipped. With the operator's lock
(`[worldview] lock = true`), per-call and per-request orders are ignored (or refused with
`conflict = "reject"`); `Disputed.locked` says so.

## Data

Natural Earth 1:10m (public domain) draws its default countries de facto and ships, for 31
countries' points of view, which admin-0 unit each polygon belongs to:

- the countries layer's `adm0_a3_xx` columns (whole polygons: Taiwan in the CN view);
- the world pack's **`worldviews` layer**: Natural Earth's 99 disputed areas (Aksai Chin,
  Arunachal Pradesh, Azad Kashmir, Gilgit-Baltistan, Shaksgam Valley, Siachen Glacier, Crimea,
  Kosovo, Western Sahara ...) drawn over the countries, each with every view's `adm0_a3_xx`. A
  point in an area takes the area's unit for the view, else the country polygon's.

Together they reproduce Natural Earth's point-of-view countries files exactly: on 800,000 random
points (half of them over South Asia) the IN and CN answers match `ne_10m_admin_0_countries_ind`
and `_chn` everywhere, so the pack ships no per-view country polygons. The layer costs 0.95 MB in
the pack (90 KB compressed). Against DataMeet's `india-composite` outline (CC0, used only as a
cross-check), the IN view agrees on 99.6% of 183,000 random land points in South Asia; the rest
are within the 1:10m generalisation of a border.

## What placewise adds (`placewise.constants.worldviews`)

| Table | Entry | Why |
|---|---|---|
| `DE_FACTO_UNITS` | Siachen Glacier (`KAS`) answers India | Natural Earth makes it its own "Indeterminate" unit; where de facto is unclear placewise leans towards India. Its code and pseudo-country name never appear in answers. |
| `UNFLAGGED_HOLDERS` | India | Disputed areas India holds (Arunachal Pradesh, Jammu and Kashmir, Demchok, Kalapani) carry no `disputed` flag. Open question: whether they should in the de facto view. |
| `VIEW_UNITS` | CN: Hong Kong and Macau answer China | Natural Earth keeps them apart even in China's view. By default both are countries, as is Taiwan. |
| `VIEW_ADMIN1` | IN: Gilgit-Baltistan, Aksai Chin, Shaksgam Valley, Siachen Glacier answer Ladakh; Azad Kashmir answers Jammu and Kashmir. De facto: Siachen Glacier answers Ladakh | Natural Earth has no point-of-view admin-1. Elsewhere admin1 is the polygon under the point (`sources["admin1"]` is `world/admin1:worldview` when a table chose it). |
| `VIEW_AREA_NAMES` | IN: Azad Kashmir is "Pakistan-occupied Kashmir" | `Disputed.name` in that view |

With the India pack installed, PIN areas give the state in India's view too (they follow India's
official boundary). The pack cuts PIN areas, and its LGD states, districts and cities, along
Natural Earth's de facto borders; the pieces flagged `india_view_only` (ground only India's view
puts in India: Gilgit-Baltistan, the part of Kashmir Pakistan administers, Aksai Chin, the
Shaksgam valley) answer only when the IN view decided the country.

## `disputed`

`Result.disputed` is set for a point in a disputed area (or whose admin1 is coded for another
country than the one it lies in, such as Crimea's `iso:UA-43`): the area's name (in the applied
view), the claimants (every view's country), who administers it, the view that was applied, each
view's answer and the lock. It is not set for a view's claim on a whole country that Natural Earth
lists no disputed area for (one view puts all of mainland China in Taiwan): Beijing is not
disputed. Taiwan itself is one of Natural Earth's disputed areas, so Taipei is.

Packs built before the `worldviews` layer fall back to whole polygons: a country polygon is
disputed when the views disagree about it, and only whole polygons switch.
