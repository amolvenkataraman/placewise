"""Hand-made Results and Entities for the display tests: public places, rounded coordinates."""

from placewise.model import BBox, Disputed, Entity, Nearby, Place, PlaceKind, Point, Relation, Result


def place(pid, name, kind, **extra):
    return Place(pid, name, kind, **extra)


def yosemite_valley():
    """A Result shaped like the lookup's answer in Yosemite Valley (values approximate)."""
    country = place("iso:US", "United States", PlaceKind.COUNTRY, codes={"iso2": "US", "iso3": "USA"})
    state = place("iso:US-CA", "California", PlaceKind.ADMIN1, codes={"iso": "US-CA", "country": "US"})
    county = place("census:06043", "Mariposa County", PlaceKind.ADMIN2)
    valley = place("census:0687000", "Yosemite Valley", PlaceKind.LOCALITY)
    park = place(
        "nps:YOSE", "Yosemite National Park", PlaceKind.PARK, tier=1, codes={"designation": "National Park"}
    )
    forest = place("usfs:0515", "Sierra National Forest", PlaceKind.PARK, tier=2)
    near = (
        Nearby(place("geonames:1", "El Portal", PlaceKind.LOCALITY), Relation.NEAR, 18.2, 260.0, "W"),
        Nearby(place("geonames:2", "Wawona", PlaceKind.LOCALITY), Relation.NEAR, 24.0, 190.0, "S"),
        Nearby(place("geonames:3", "Mariposa", PlaceKind.LOCALITY), Relation.NEAR, 48.6, 225.0, "SW"),
        Nearby(place("geonames:4", "Oakhurst", PlaceKind.LOCALITY), Relation.NEAR, 50.1, 200.0, "S"),
    )
    return Result(
        lat=37.7284,
        lon=-119.6115,
        label="Yosemite Valley, Yosemite National Park",
        country=country,
        admin1=state,
        admin2=county,
        city=valley,
        locality=valley,
        postal=place("zcta:95389", "95389", PlaceKind.POSTAL_CODE),
        tz="America/Los_Angeles",
        within=(park, forest),
        near=near,
        sources={
            "country": "world/countries:polygon",
            "admin1": "usa/states:polygon",
            "admin2": "usa/counties:polygon",
            "city": "usa/places:polygon",
            "locality": "usa/places:polygon",
            "postal": "usa/zcta:polygon",
            "tz": "usa/timezones:polygon",
            "within": "usa-parks/parks_national:polygon",
            "near": "world/cities:nearest",
        },
        data_version="world-2026.11+usa-2026.11",
    )


def lake_answer():
    """On a lake, with an airport near: the water and airport rows."""
    lake = place("water:tahoe", "Lake Tahoe", PlaceKind.WATER, codes={"type": "lake"})
    airport = place("ourairports:KTVL", "Lake Tahoe Airport", PlaceKind.AIRPORT, codes={"iata": "TVL"})
    return Result(
        lat=39.1211,
        lon=-120.0362,
        label="On Lake Tahoe",
        country=place("iso:US", "United States", PlaceKind.COUNTRY, codes={"iso2": "US"}),
        water=Nearby(lake, Relation.ON, 6.7, 90.0, "E"),  # 6.7 km to the shore
        airport=Nearby(airport, Relation.NEAR, 9.04, 160.0, "SE"),
        sources={"water": "world-water/lakes:polygon", "airport": "world/airports:nearest"},
    )


def disputed_answer():
    return Result(
        lat=34.0,
        lon=77.0,
        label="Somewhere",
        disputed=Disputed("An Area", ("XA", "XB"), administered_by="XA", views={"XA": "XA", "XB": "XB"}),
    )


def paris_texas():
    town = place(
        "geonames:4717560",
        "Paris",
        PlaceKind.LOCALITY,
        source="geonames",
        codes={"iso2": "US", "admin1": "TX"},
        aliases=("Paris, Texas",),
    )
    alternates = (
        place("census:4855000", "Paris", PlaceKind.LOCALITY),
        place("x:1", "Paris", PlaceKind.REGION),
    )
    return Entity(
        place=town,
        point=Point(33.66094, -95.55551),
        bbox=BBox(33.6, -95.62, 33.72, -95.48),
        radius_km=8.4,
        region="Texas",
        country="US",
        score=0.9123,
        alternates=alternates,
    )
