"""GENERATED from datasets/regions by packbuild.regions; do not edit.

Metro and vernacular regions ("GTA", "SF Bay Area", "NYC", "Delhi NCR"): id, short name, name,
country, admin1 codes, aliases, principal cities with their admin1, and other names of those
cities. Regenerate with `uv run python -m packbuild.regions`.
"""

from ._records import Metro

# fmt: off
REGIONS = (
    Metro(
        id="region:gta",
        key="GTA", name="Greater Toronto Area", country="CA",
        admin1=("ON",),
        aliases=(
            "Greater Toronto", "Toronto Area", "Toronto Metro", "GTHA", "Greater Toronto and Hamilton Area",
            "Greater Toronto Hamilton Area",
        ),
        cities={
            "Toronto": "ON", "North York": "ON", "Scarborough": "ON", "Etobicoke": "ON",
            "Mississauga": "ON", "Brampton": "ON", "Markham": "ON", "Vaughan": "ON", "Richmond Hill": "ON",
            "Oakville": "ON", "Burlington": "ON", "Milton": "ON", "Oshawa": "ON", "Whitby": "ON",
            "Ajax": "ON", "Pickering": "ON", "Newmarket": "ON", "Aurora": "ON", "Caledon": "ON",
            "Hamilton": "ON",
        },
    ),
    Metro(
        id="region:golden-horseshoe",
        key="Golden Horseshoe", name="Greater Golden Horseshoe", country="CA",
        admin1=("ON",),
        aliases=(
            "GGH", "Greater Golden Horseshoe Area",
        ),
    ),
    Metro(
        id="region:metro-vancouver",
        key="Metro Vancouver", name="Metro Vancouver", country="CA",
        admin1=("BC",),
        aliases=(
            "Greater Vancouver", "Greater Vancouver Area", "Vancouver Area", "Vancouver Metro",
        ),
        cities={
            "Vancouver": "BC", "Burnaby": "BC", "Surrey": "BC", "Richmond": "BC", "Coquitlam": "BC",
            "North Vancouver": "BC", "West Vancouver": "BC", "New Westminster": "BC", "Delta": "BC",
            "Langley": "BC", "Port Moody": "BC", "Maple Ridge": "BC",
        },
    ),
    Metro(
        id="region:greater-montreal",
        key="Greater Montreal", name="Greater Montreal", country="CA",
        admin1=("QC",),
        aliases=(
            "Montreal Area", "Montreal Metro", "Grand Montréal", "Montreal Metropolitan Community",
        ),
        cities={
            "Montreal": "QC", "Montréal": "QC", "Laval": "QC", "Longueuil": "QC", "Brossard": "QC",
            "Terrebonne": "QC", "Saint-Laurent": "QC",
        },
    ),
    Metro(
        id="region:ottawa-gatineau",
        key="Ottawa-Gatineau", name="National Capital Region (Canada)", country="CA",
        admin1=("ON", "QC",),
        aliases=(
            "Ottawa Gatineau", "National Capital Region of Canada", "Canada's Capital Region",
            "Ottawa Area",
        ),
        cities={
            "Ottawa": "ON", "Kanata": "ON", "Nepean": "ON", "Gatineau": "QC",
        },
    ),
    Metro(
        id="region:waterloo-region",
        key="Waterloo Region", name="Waterloo Region", country="CA",
        admin1=("ON",),
        aliases=(
            "Region of Waterloo", "Kitchener-Waterloo", "Kitchener Waterloo",
            "Kitchener-Waterloo-Cambridge",
        ),
        cities={
            "Kitchener": "ON", "Waterloo": "ON", "Cambridge": "ON",
        },
    ),
    Metro(
        id="region:greater-london",
        key="Greater London", name="Greater London", country="GB",
        admin1=("ENG",),
        aliases=(
            "London Area", "London Metropolitan Area",
        ),
        cities={
            "London": "ENG",
        },
    ),
    Metro(
        id="region:delhi-ncr",
        key="NCR", name="National Capital Region (India)", country="IN",
        admin1=("DL", "HR", "UP", "RJ",),
        aliases=(
            "Delhi NCR", "Delhi-NCR", "NCR Delhi", "National Capital Region",
            "Delhi National Capital Region", "Delhi NCR core", "Delhi NCR (core)", "Central NCR",
            "Core NCR",
        ),
        cities={
            "New Delhi": "DL", "Delhi": "DL", "Gurugram": "HR", "Faridabad": "HR", "Noida": "UP",
            "Greater Noida": "UP", "Ghaziabad": "UP",
        },
    ),
    Metro(
        id="region:mumbai-metro-region",
        key="MMR", name="Mumbai Metropolitan Region", country="IN",
        admin1=("MH",),
        aliases=(
            "Mumbai Metropolitan Region", "Mumbai Metro", "Mumbai Area",
        ),
        cities={
            "Mumbai": "MH", "Thane": "MH", "Navi Mumbai": "MH",
        },
    ),
    Metro(
        id="region:bengaluru",
        key="Bengaluru", name="Bengaluru", country="IN",
        admin1=("KA",),
        aliases=(
            "Bengaluru Urban", "Bangalore Urban", "Greater Bengaluru", "Bengaluru Area", "Bangalore Area",
            "Bengaluru Metropolitan Region", "Bangalore Metropolitan Region", "BMR", "BMRDA Region",
        ),
        cities={
            "Bengaluru": "KA",
        },
    ),
    Metro(
        id="region:sf-bay-area",
        key="Bay Area", name="San Francisco Bay Area", country="US",
        admin1=("CA",),
        aliases=(
            "SF Bay Area", "SFBA", "San Francisco Bay Area", "SF Bay", "Silicon Valley", "Bay Area Region",
        ),
        cities={
            "San Francisco": "CA", "South San Francisco": "CA", "Oakland": "CA", "Berkeley": "CA",
            "Emeryville": "CA", "San Jose": "CA", "Palo Alto": "CA", "Mountain View": "CA",
            "Sunnyvale": "CA", "Santa Clara": "CA", "Menlo Park": "CA", "Redwood City": "CA",
            "Cupertino": "CA", "Fremont": "CA", "San Mateo": "CA", "Milpitas": "CA", "Foster City": "CA",
            "Burlingame": "CA", "San Bruno": "CA", "Hayward": "CA", "Pleasanton": "CA",
            "Walnut Creek": "CA", "Los Gatos": "CA", "Los Altos": "CA", "San Carlos": "CA", "Belmont": "CA",
            "Campbell": "CA", "Livermore": "CA", "Daly City": "CA", "San Rafael": "CA", "San Ramon": "CA",
            "San Leandro": "CA", "Napa": "CA", "Santa Rosa": "CA",
        },
    ),
    Metro(
        id="region:greater-los-angeles",
        key="Greater Los Angeles", name="Greater Los Angeles", country="US",
        admin1=("CA",),
        aliases=(
            "Greater LA", "LA Metro", "Los Angeles Metro", "Los Angeles Area", "LA Area",
            "Los Angeles Metropolitan Area",
        ),
        cities={
            "Los Angeles": "CA", "Santa Monica": "CA", "Pasadena": "CA", "Burbank": "CA",
            "Long Beach": "CA", "Irvine": "CA", "Anaheim": "CA", "Santa Ana": "CA", "Culver City": "CA",
            "El Segundo": "CA", "Torrance": "CA", "Hawthorne": "CA", "Costa Mesa": "CA",
            "Newport Beach": "CA", "Huntington Beach": "CA",
        },
    ),
    Metro(
        id="region:new-york-metro",
        key="NYC", name="New York metropolitan area", country="US",
        admin1=("NY", "NJ", "CT", "PA",),
        aliases=(
            "New York Metro", "NYC Metro", "NY Metro", "New York Metropolitan Area", "Greater New York",
            "Tri-State Area", "New York Area", "NYC Area", "New York City Metropolitan Area",
        ),
        cities={
            "New York City": "NY", "Manhattan": "NY", "Brooklyn": "NY", "Queens": "NY", "Bronx": "NY",
            "Staten Island": "NY", "Long Island City": "NY", "White Plains": "NY", "Yonkers": "NY",
            "Jersey City": "NJ", "Newark": "NJ", "Hoboken": "NJ", "Edison": "NJ", "Morristown": "NJ",
            "Stamford": "CT", "Greenwich": "CT",
        },
    ),
    Metro(
        id="region:greater-boston",
        key="Greater Boston", name="Greater Boston", country="US",
        admin1=("MA", "NH",),
        aliases=(
            "Greater Boston Area", "Boston Area", "Boston Metro", "Metro Boston",
            "Boston Metropolitan Area",
        ),
        cities={
            "Boston": "MA", "Cambridge": "MA", "Somerville": "MA", "Waltham": "MA", "Newton": "MA",
            "Quincy": "MA", "Burlington": "MA", "Woburn": "MA", "Needham": "MA", "Wellesley": "MA",
            "Framingham": "MA", "Lowell": "MA", "Brookline": "MA", "Watertown": "MA", "Lexington": "MA",
        },
    ),
    Metro(
        id="region:greater-seattle",
        key="Greater Seattle", name="Greater Seattle", country="US",
        admin1=("WA",),
        aliases=(
            "Greater Seattle Area", "Seattle Area", "Seattle Metro", "Seattle Metropolitan Area",
            "Puget Sound", "Puget Sound Region",
        ),
        cities={
            "Seattle": "WA", "Bellevue": "WA", "Redmond": "WA", "Kirkland": "WA", "Tacoma": "WA",
            "Everett": "WA", "Bothell": "WA", "Renton": "WA", "Issaquah": "WA", "Kent": "WA",
            "Sammamish": "WA", "Lynnwood": "WA", "Woodinville": "WA", "Federal Way": "WA",
        },
    ),
    Metro(
        id="region:dallas-fort-worth",
        key="DFW", name="Dallas-Fort Worth metroplex", country="US",
        admin1=("TX",),
        aliases=(
            "Dallas-Fort Worth", "Dallas Fort Worth", "Dallas/Fort Worth", "Metroplex", "DFW Metroplex",
            "Dallas-Fort Worth Metroplex", "DFW Area", "Dallas Area",
        ),
        cities={
            "Dallas": "TX", "Fort Worth": "TX", "Arlington": "TX", "Plano": "TX", "Irving": "TX",
            "Frisco": "TX", "Richardson": "TX", "Garland": "TX", "McKinney": "TX", "Denton": "TX",
            "Addison": "TX", "Carrollton": "TX", "Grapevine": "TX", "Southlake": "TX", "Allen": "TX",
            "Lewisville": "TX", "Coppell": "TX",
        },
    ),
    Metro(
        id="region:greater-houston",
        key="Greater Houston", name="Greater Houston", country="US",
        admin1=("TX",),
        aliases=(
            "Houston Area", "Houston Metro", "Houston Metropolitan Area",
        ),
        cities={
            "Houston": "TX", "The Woodlands": "TX", "Sugar Land": "TX", "Katy": "TX", "Pearland": "TX",
        },
    ),
    Metro(
        id="region:washington-metro",
        key="DMV", name="Washington metropolitan area", country="US",
        admin1=("DC", "MD", "VA", "WV",),
        aliases=(
            "DC Metro", "DC Metro Area", "DC Area", "Washington DC Metro", "Washington DC Area",
            "Washington Metropolitan Area", "Greater Washington", "Washington DC Metropolitan Area",
        ),
        cities={
            "Washington": "DC", "Arlington": "VA", "Alexandria": "VA", "Reston": "VA", "Herndon": "VA",
            "McLean": "VA", "Tysons": "VA", "Fairfax": "VA", "Chantilly": "VA", "Bethesda": "MD",
            "Rockville": "MD", "Silver Spring": "MD", "Gaithersburg": "MD", "College Park": "MD",
        },
    ),
    Metro(
        id="region:greater-philadelphia",
        key="Greater Philadelphia", name="Greater Philadelphia", country="US",
        admin1=("PA", "NJ", "DE", "MD",),
        aliases=(
            "Philadelphia Area", "Philadelphia Metro", "Philly Area", "Delaware Valley",
        ),
        cities={
            "Philadelphia": "PA", "King of Prussia": "PA", "Conshohocken": "PA", "Camden": "NJ",
            "Cherry Hill": "NJ", "Wilmington": "DE",
        },
    ),
    Metro(
        id="region:chicagoland",
        key="Chicagoland", name="Chicago metropolitan area", country="US",
        admin1=("IL", "IN", "WI",),
        aliases=(
            "Chicago Area", "Greater Chicago", "Chicago Metro", "Chicago Metro Area",
            "Chicago Metropolitan Area",
        ),
        cities={
            "Chicago": "IL", "Evanston": "IL", "Naperville": "IL", "Schaumburg": "IL", "Oak Brook": "IL",
            "Skokie": "IL", "Deerfield": "IL", "Northbrook": "IL", "Gary": "IN", "Hammond": "IN",
            "Kenosha": "WI",
        },
    ),
    Metro(
        id="region:metro-atlanta",
        key="Metro Atlanta", name="Metro Atlanta", country="US",
        admin1=("GA",),
        aliases=(
            "Atlanta Metro", "Greater Atlanta", "Atlanta Area", "Atlanta Metropolitan Area",
        ),
        cities={
            "Atlanta": "GA", "Alpharetta": "GA", "Marietta": "GA", "Sandy Springs": "GA", "Decatur": "GA",
            "Kennesaw": "GA", "Norcross": "GA", "Duluth": "GA",
        },
    ),
    Metro(
        id="region:twin-cities",
        key="Twin Cities", name="Minneapolis–Saint Paul", country="US",
        admin1=("MN", "WI",),
        aliases=(
            "Minneapolis-Saint Paul", "Minneapolis-St. Paul", "Minneapolis St Paul", "Minneapolis-St Paul",
            "MSP Area",
        ),
        cities={
            "Minneapolis": "MN", "Saint Paul": "MN", "St. Paul": "MN", "Bloomington": "MN",
            "Eden Prairie": "MN", "Edina": "MN", "Eagan": "MN", "Maple Grove": "MN",
        },
    ),
    Metro(
        id="region:research-triangle",
        key="Research Triangle", name="Research Triangle", country="US",
        admin1=("NC",),
        aliases=(
            "RTP", "Research Triangle Park", "The Triangle", "Triangle Area", "Raleigh-Durham",
            "Raleigh Durham",
        ),
        cities={
            "Raleigh": "NC", "Durham": "NC", "Chapel Hill": "NC", "Cary": "NC", "Morrisville": "NC",
            "Apex": "NC",
        },
    ),
    Metro(
        id="region:las-vegas",
        key="Greater Las Vegas", name="Las Vegas metropolitan area", country="US",
        admin1=("NV",),
        aliases=(
            "Las Vegas Metro", "Las Vegas Area", "Las Vegas Metropolitan Area", "Las Vegas Valley",
        ),
    ),
)
# fmt: on
