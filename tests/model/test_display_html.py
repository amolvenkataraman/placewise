"""The notebook view of Results and Entities (`_repr_html_`): placewise.model.display.html."""

import dataclasses
import re
from html.parser import HTMLParser

from display_kit import paris_texas, yosemite_valley


class Table(HTMLParser):
    """The caption text and the rows' cell texts of a table, plus every tag and attribute seen."""

    def __init__(self, text):
        super().__init__()
        self.caption, self.rows, self.tags, self.attrs = "", [], [], []
        self._cell = self._in_caption = None
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs += attrs
        if tag == "tr":
            self.rows.append([])
        elif tag in ("th", "td"):
            self._cell = ""
        elif tag == "caption":
            self._in_caption = True

    def handle_endtag(self, tag):
        if tag in ("th", "td"):
            self.rows[-1].append(self._cell)
            self._cell = None
        elif tag == "caption":
            self._in_caption = False

    def handle_data(self, data):
        if self._cell is not None:
            self._cell += data
        elif self._in_caption:
            self.caption += data


def test_result_table_has_the_card_rows():
    t = Table(yosemite_valley()._repr_html_())
    assert t.caption == "Yosemite Valley, Yosemite National Park(37.72840, -119.61150)"
    assert t.rows[0] == ["locality", "Yosemite Valley", "usa/places:polygon"]
    assert [
        "within",
        "Yosemite National Park · Sierra National Forest",
        "usa-parks/parks_national:polygon",
    ] in t.rows
    assert [r[0] for r in t.rows] == [
        "locality",
        "city",
        "admin2",
        "admin1",
        "country",
        "postal",
        "within",
        "near",
        "tz",
    ]


def test_entity_table():
    t = Table(paris_texas()._repr_html_())
    assert t.caption == "Paris(Texas, US)"
    assert ["id", "geonames:4717560", "geonames"] in t.rows and ["kind", "locality", ""] in t.rows


def test_no_external_assets_no_fixed_colours_and_escaped():
    r = dataclasses.replace(yosemite_valley(), label="<script>alert(1)</script> & co")
    html = r._repr_html_()
    t = Table(html)
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert set(t.tags) <= {"table", "caption", "span", "tbody", "tr", "th", "td"}
    styles = " ".join(v for k, v in t.attrs if k == "style")
    assert not any(k in ("src", "href") for k, _ in t.attrs) and "url(" not in styles
    # colours come from the theme: only "inherit" and opacity, never a colour value
    assert not re.search(r"#[0-9a-f]{3}|rgb|hsl", styles, re.IGNORECASE)
    assert "color:inherit" in styles and "opacity" in styles
