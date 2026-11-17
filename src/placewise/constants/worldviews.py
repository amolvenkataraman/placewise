"""Worldviews: the disputed-areas layer and the small curated tables applied on top of Natural Earth.

Natural Earth's countries file and its disputed-areas file carry, per view XX, the admin-0 unit
the view puts each polygon in (`adm0_a3_xx`). These tables cover what Natural Earth leaves open.
Each entry is a deliberate choice, documented in docs/worldviews.md.
"""

WORLDVIEWS = "worldviews"  # the world pack's layer of Natural Earth disputed areas (one row per area)
# Result.sources rule for an admin1 a view's table chose ("world/admin1:worldview")
WORLDVIEW_RULE = "worldview"

# Natural Earth units that are nobody's country, answered de facto as the unit that holds the
# ground. Where de facto is unclear, placewise leans towards India: Siachen Glacier ("KAS",
# Natural Earth's "Indeterminate" unit) is held by India. The unit's own code never appears in
# answers.
DE_FACTO_UNITS = {"KAS": "IND"}

# Disputed areas held by these units carry no `disputed` flag (owner policy: India-held areas are
# not reported as disputed; see docs/worldviews.md, open question).
UNFLAGGED_HOLDERS = frozenset({"IND"})

# Per view, units the view answers as another unit where Natural Earth keeps them apart:
# with the CN view, Hong Kong and Macau answer China.
VIEW_UNITS = {"CN": {"HKG": "CHN", "MAC": "CHN"}}

# Per view ("de_facto" or a view code), the admin1 id a disputed area answers (by area name, as the
# worldviews layer spells it). Areas not listed keep the admin1 polygon under them, or none when that
# belongs to another country than the one the view reports.
VIEW_ADMIN1 = {
    "de_facto": {"Siachen Glacier": "iso:IN-LA"},
    "IN": {
        "Gilgit-Baltistan": "iso:IN-LA",
        "Aksai Chin": "iso:IN-LA",
        "Shaksgam Valley": "iso:IN-LA",
        "Siachen Glacier": "iso:IN-LA",
        "Azad Kashmir": "iso:IN-JK",
    },
}

# Per view, the name a disputed area goes by in that view (Disputed.name).
VIEW_AREA_NAMES = {"IN": {"Azad Kashmir": "Pakistan-occupied Kashmir"}}

# A country pack column flagging features on ground only one view gives that country: the India
# pack's PIN areas outside de facto India answer only when the IN view decided the country.
IND_VIEW_ONLY = "india_view_only"

# Build time: Natural Earth 5.1.2 spellings corrected in the worldviews layer.
AREA_NAMES = {"Shaksam Valley": "Shaksgam Valley", "Ilemi Triange": "Ilemi Triangle"}
