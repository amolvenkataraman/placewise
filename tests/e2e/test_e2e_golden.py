"""A golden set of well-known public places in the US, Canada and India (landmarks, city halls,
legislatures, airports, campuses, park visitor centres): country, admin1, locality and city over
the real packs. None means "no locality" (unincorporated or unorganised land)."""

import pytest
from e2e_kit import geocoder

# name, (lat, lon), country, admin1 id, locality, city
GOLDEN = [
    # United States
    ("Statue of Liberty", (40.6892, -74.0445), "US", "iso:US-NY", "New York", "New York"),
    ("Empire State Building", (40.7484, -73.9857), "US", "iso:US-NY", "New York", "New York"),
    ("JFK Airport", (40.6413, -73.7781), "US", "iso:US-NY", "New York", "New York"),
    ("White House", (38.8977, -77.0365), "US", "iso:US-DC", "Washington", "Washington"),
    ("The Pentagon", (38.8719, -77.0563), "US", "iso:US-VA", "Arlington", "Arlington"),
    ("Golden Gate Welcome Center", (37.8078, -122.4750), "US", "iso:US-CA", "San Francisco", "San Francisco"),
    ("Space Needle", (47.6205, -122.3493), "US", "iso:US-WA", "Seattle", "Seattle"),
    ("Seattle-Tacoma Airport", (47.4502, -122.3088), "US", "iso:US-WA", "SeaTac", "SeaTac"),
    ("Willis Tower", (41.8789, -87.6359), "US", "iso:US-IL", "Chicago", "Chicago"),
    ("Hollywood Sign", (34.1341, -118.3215), "US", "iso:US-CA", "Los Angeles", "Los Angeles"),
    ("LAX", (33.9416, -118.4085), "US", "iso:US-CA", "Los Angeles", "Los Angeles"),
    ("UCLA", (34.0729, -118.4422), "US", "iso:US-CA", "Los Angeles", "Los Angeles"),
    ("Disneyland", (33.8121, -117.9190), "US", "iso:US-CA", "Anaheim", "Anaheim"),
    ("Stanford University", (37.4275, -122.1697), "US", "iso:US-CA", "Stanford", "Stanford"),
    ("Harvard Yard", (42.3744, -71.1169), "US", "iso:US-MA", "Cambridge", "Cambridge"),
    ("MIT", (42.3601, -71.0942), "US", "iso:US-MA", "Cambridge", "Cambridge"),
    ("Boston City Hall", (42.3603, -71.0580), "US", "iso:US-MA", "Boston", "Boston"),
    ("Philadelphia City Hall", (39.9524, -75.1636), "US", "iso:US-PA", "Philadelphia", "Philadelphia"),
    ("Georgia State Capitol", (33.7490, -84.3880), "US", "iso:US-GA", "Atlanta", "Atlanta"),
    ("Texas State Capitol", (30.2747, -97.7404), "US", "iso:US-TX", "Austin", "Austin"),
    ("Denver Union Station", (39.7527, -104.9997), "US", "iso:US-CO", "Denver", "Denver"),
    ("Las Vegas City Hall", (36.1676, -115.1488), "US", "iso:US-NV", "Las Vegas", "Las Vegas"),
    ("Las Vegas Strip", (36.1147, -115.1728), "US", "iso:US-NV", "Las Vegas", "Las Vegas"),
    ("Miami Beach", (25.7907, -80.1300), "US", "iso:US-FL", "Miami Beach", "Miami Beach"),
    ("Yosemite Valley Visitor Center", (37.7487, -119.5873), "US", "iso:US-CA", "Yosemite Valley",
     "Yosemite Valley"),
    ("Grand Canyon Visitor Center", (36.0590, -112.1090), "US", "iso:US-AZ", "Grand Canyon Village",
     "Grand Canyon Village"),
    ("SFO", (37.6155, -122.39), "US", "iso:US-CA", None, "San Francisco"),
    # Canada
    ("CN Tower", (43.6426, -79.3871), "CA", "iso:CA-ON", "Toronto", "Toronto"),
    ("Parliament Hill", (45.4236, -75.7009), "CA", "iso:CA-ON", "Ottawa", "Ottawa"),
    ("Canadian Museum of History", (45.4299, -75.7090), "CA", "iso:CA-QC", "Gatineau", "Gatineau"),
    ("Montreal City Hall", (45.5088, -73.5540), "CA", "iso:CA-QC", "Montréal", "Montréal"),
    ("Chateau Frontenac", (46.8122, -71.2050), "CA", "iso:CA-QC", "Québec", "Québec"),
    ("Vancouver City Hall", (49.2606, -123.1140), "CA", "iso:CA-BC", "Vancouver", "Vancouver"),
    ("BC Legislature", (48.4196, -123.3700), "CA", "iso:CA-BC", "Victoria", "Victoria"),
    ("Whistler Village", (50.1163, -122.9574), "CA", "iso:CA-BC", "Whistler", "Whistler"),
    ("Calgary Tower", (51.0443, -114.0631), "CA", "iso:CA-AB", "Calgary", "Calgary"),
    ("Alberta Legislature", (53.5336, -113.5065), "CA", "iso:CA-AB", "Edmonton", "Edmonton"),
    ("Banff Avenue", (51.1784, -115.5708), "CA", "iso:CA-AB", "Banff", "Banff"),
    ("Saskatchewan Legislature", (50.4320, -104.6150), "CA", "iso:CA-SK", "Regina", "Regina"),
    ("The Forks, Winnipeg", (49.8873, -97.1308), "CA", "iso:CA-MB", "Winnipeg", "Winnipeg"),
    ("Halifax Citadel", (44.6475, -63.5806), "CA", "iso:CA-NS", "Halifax", "Halifax"),
    ("Signal Hill", (47.5695, -52.6818), "CA", "iso:CA-NL", "St. John's", "St. John's"),
    ("Square One", (43.5933, -79.6421), "CA", "iso:CA-ON", "Mississauga", "Mississauga"),
    ("Brampton City Hall", (43.6858, -79.7599), "CA", "iso:CA-ON", "Brampton", "Brampton"),
    ("Pickering City Hall", (43.8384, -79.0868), "CA", "iso:CA-ON", "Pickering", "Toronto"),
    ("University of Waterloo", (43.4723, -80.5449), "CA", "iso:CA-ON", "Waterloo", "Waterloo"),
    ("Cambridge City Hall", (43.3601, -80.3127), "CA", "iso:CA-ON", "Cambridge", "Cambridge"),
    ("Kingston City Hall", (44.2312, -76.4800), "CA", "iso:CA-ON", "Kingston", "Kingston"),
    ("Clifton Hill", (43.0910, -79.0760), "CA", "iso:CA-ON", "Niagara Falls", "Niagara Falls"),
    # India
    ("India Gate", (28.6129, 77.2295), "IN", "iso:IN-DL", "Delhi", "Delhi"),
    ("Gateway of India", (18.9220, 72.8347), "IN", "iso:IN-MH", "Mumbai", "Mumbai"),
    ("IIT Bombay", (19.1334, 72.9133), "IN", "iso:IN-MH", "Mumbai", "Mumbai"),
    ("Shaniwar Wada", (18.5195, 73.8553), "IN", "iso:IN-MH", "Pune", "Pune"),
    ("Charminar", (17.3616, 78.4747), "IN", "iso:IN-TG", "Hyderabad", "Hyderabad"),
    ("HITEC City", (17.4435, 78.3772), "IN", "iso:IN-TG", "Hyderabad", "Hyderabad"),
    ("Victoria Memorial", (22.5448, 88.3426), "IN", "iso:IN-WB", "Kolkata", "Kolkata"),
    ("Marina Beach", (13.0500, 80.2824), "IN", "iso:IN-TN", "Chennai", "Chennai"),
    ("Vidhana Soudha", (12.9791, 77.5913), "IN", "iso:IN-KA", "Bengaluru", "Bengaluru"),
    ("Kempegowda Airport", (13.1986, 77.7066), "IN", "iso:IN-KA", "Bengaluru", "Bengaluru"),
    ("Mysuru Palace", (12.3052, 76.6552), "IN", "iso:IN-KA", "Mysuru", "Mysuru"),
    ("Hawa Mahal", (26.9239, 75.8267), "IN", "iso:IN-RJ", "Jaipur", "Jaipur"),
    ("Taj Mahal", (27.1751, 78.0421), "IN", "iso:IN-UP", "Agra", "Agra"),
    ("Bara Imambara", (26.8692, 80.9124), "IN", "iso:IN-UP", "Lucknow", "Lucknow"),
    ("Noida Sector 18", (28.5708, 77.3260), "IN", "iso:IN-UP", "Noida", "Noida"),
    ("Cyber City, Gurugram", (28.495, 77.089), "IN", "iso:IN-HR", "Gurugram", "Gurugram"),
    ("Golden Temple", (31.6200, 74.8765), "IN", "iso:IN-PB", "Amritsar", "Amritsar"),
    ("Chandigarh Capitol Complex", (30.7590, 76.8060), "IN", "iso:IN-CH", "Chandigarh", "Chandigarh"),
    ("Sabarmati Ashram", (23.0607, 72.5806), "IN", "iso:IN-GJ", "Ahmedabad", "Ahmedabad"),
    ("Lingaraj Temple", (20.2382, 85.8338), "IN", "iso:IN-OR", "Bhubaneswar", "Bhubaneswar"),
    ("Kamakhya Temple", (26.1664, 91.7055), "IN", "iso:IN-AS", "Guwahati", "Guwahati"),
]  # fmt: skip


@pytest.fixture(scope="module")
def geo():
    return geocoder("world", "usa", "can", "ind")


@pytest.mark.parametrize(
    ("name", "point", "cc", "admin1", "locality", "city"), GOLDEN, ids=[g[0] for g in GOLDEN]
)
def test_golden(geo, name, point, cc, admin1, locality, city):
    r = geo.lookup(*point)
    got = (r.cc, r.admin1 and r.admin1.id, r.locality and r.locality.name, r.city and r.city.name)
    assert got == (cc, admin1, locality, city)


def test_golden_set_is_large_and_spread():
    by_country = {}
    for g in GOLDEN:
        by_country[g[2]] = by_country.get(g[2], 0) + 1
    assert len(GOLDEN) >= 40 and min(by_country.values()) >= 15


def test_golden_batch_equals_single(geo):
    lats, lons = [g[1][0] for g in GOLDEN], [g[1][1] for g in GOLDEN]
    many = geo.lookup_many(lats, lons)
    assert [r.to_dict() for r in many] == [
        geo.lookup(a, b).to_dict() for a, b in zip(lats, lons, strict=True)
    ]
