"""Small inputs for the park sources: ArcGIS query pages, a USFS shapefile and Wikidata results.

Invented parks in open Pacific water (around 0°N 140°W, as lookup_kit's world), except where a
real projection needs a real place: the CPCAD pages use synthetic boxes near 45°N 80°W.
"""

import json

from us_fixtures import NAD83_PRJ, write_shapefile

from packbuild.sources.parks.cpcad import CANADA_ATLAS_LAMBERT
from placewise.geo import to_web_mercator


def mercator_box(south, west, north, east):
    """A clockwise ring (outer, as Esri JSON wants) in Web Mercator metres."""
    corners = [(south, west), (north, west), (north, east), (south, east), (south, west)]
    return [list(map(float, to_web_mercator(lat, lon))) for lat, lon in corners]


def lambert_box(south, west, north, east):
    corners = [(south, west), (north, west), (north, east), (south, east), (south, west)]
    return [list(map(float, CANADA_ATLAS_LAMBERT.forward(lon, lat))) for lat, lon in corners]


def write_pages(folder, features, page_size=2):
    """features: [(attributes, [ring, ...]), ...] as query pages in `folder`."""
    folder.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(features), page_size):
        page = {
            "features": [{"attributes": a, "geometry": {"rings": r}} for a, r in features[k : k + page_size]]
        }
        (folder / f"page-{k // page_size:04d}.json").write_text(json.dumps(page))
    return folder


def nps_pages(folder):
    unit = {"STATE": "XX", "REGION": "PW"}
    return write_pages(folder, [
        ({**unit, "UNIT_CODE": "ALPH", "UNIT_NAME": "Alpha National Park", "UNIT_TYPE": "National Parks",
          "PARKNAME": "Alpha"}, [mercator_box(0.6, -139.9, 0.9, -139.6)]),
        ({**unit, "UNIT_CODE": "ALPH", "UNIT_NAME": "Alpha National Preserve", "UNIT_TYPE": "National Preserves",  # noqa: E501
          "PARKNAME": "Alpha"}, [mercator_box(0.9, -139.9, 0.95, -139.6)]),
        ({**unit, "UNIT_CODE": "TINY", "UNIT_NAME": "Tiny Rock National Monument",
          "UNIT_TYPE": "National Monuments", "PARKNAME": ""}, [mercator_box(0.1, -139.1, 0.11, -139.09)]),
        ({**unit, "UNIT_CODE": "BIGM", "UNIT_NAME": "Big Mesa National Monument",
          "UNIT_TYPE": "National Monuments", "PARKNAME": ""}, [mercator_box(0.2, -139.5, 0.3, -139.4)]),
        ({**unit, "UNIT_CODE": "OLDH", "UNIT_NAME": "Old House National Historic Site",
          "UNIT_TYPE": "National Historic Sites", "PARKNAME": ""}, [mercator_box(0.4, -139.2, 0.41, -139.19)]),  # noqa: E501
        ({**unit, "UNIT_CODE": "XXXX", "UNIT_NAME": "Mystery Unit", "UNIT_TYPE": "Something New",
          "PARKNAME": ""}, [mercator_box(0.5, -139.2, 0.51, -139.19)]),
    ])  # fmt: skip


def padus_fee_pages(folder):
    def parcel(oid, name, des_tp, box, access="OA", manager="CITY", state="XX", local=""):
        attrs = {"OBJECTID": oid, "Unit_Nm": name, "Des_Tp": des_tp, "Pub_Access": access, "Mang_Name": manager,  # noqa: E501
                 "State_Nm": state, "Loc_Nm": local}  # fmt: skip
        return attrs, [mercator_box(*box)]

    return write_pages(folder, [
        parcel(1, "Central Green", "LP", (0.100, -139.300, 0.105, -139.295)),
        parcel(2, "Central Green", "LP", (0.106, -139.300, 0.110, -139.295)),  # 110 m away: same park
        parcel(3, "Central Green", "LP", (0.500, -139.300, 0.505, -139.295)),  # 44 km away: another park
        parcel(4, "Gull State Park", "SP", (0.20, -139.20, 0.25, -139.15), manager="SPR"),
        parcel(5, "Closed Yard", "LP", (0.30, -139.30, 0.31, -139.29), access="XA"),
        parcel(6, "City of Nowhere", "LP", (0.32, -139.30, 0.33, -139.29)),
        parcel(7, "Private Woods", "PCON", (0.34, -139.30, 0.35, -139.29)),
        parcel(8, "Agency Monument", "NM", (0.36, -139.30, 0.37, -139.29), manager="NPS"),
        parcel(9, "Mesa Monument", "NM", (0.38, -139.30, 0.39, -139.29), manager="BLM"),
        # generic names: the parcel's local name when it has a real one, else nothing
        parcel(10, "Open Space", "LP", (0.40, -139.30, 0.41, -139.29), local="Heron Ridge Open Space"),
        parcel(11, "Unknown Park", "LP", (0.42, -139.30, 0.43, -139.29), local="Unknown Park"),
        parcel(12, "Open  space", "LCA", (0.44, -139.30, 0.45, -139.29)),
        parcel(13, "Unknown", "LP", (0.46, -139.30, 0.47, -139.29), local="Willow Bend Park"),
    ])  # fmt: skip


def padus_refuge_pages(folder):
    attrs = {"OBJECTID": 1, "Unit_Nm": "Heron National Wildlife Refuge", "Des_Tp": "PROC", "Loc_Ds": "NWR",
             "Mang_Name": "FWS", "Pub_Access": "UK", "State_Nm": "XX"}  # fmt: skip
    return write_pages(folder, [(attrs, [mercator_box(0.7, -139.3, 0.8, -139.2)])])


def cpcad_pages(folder):
    def zone(zone_id, parent, name, kind, box, owner=1, gov=1, pa=1, status=1):
        attrs = {"ZONE_ID": zone_id, "PARENT_ID": parent, "NAME_E": name, "TYPE_E": kind, "OWNER_TYPE": owner,
                 "GOV_TYPE": gov, "PA_OECM_DF": pa, "STATUS": status, "O_AREA_HA": 100}  # fmt: skip
        return attrs, [lambert_box(*box)]

    return write_pages(folder, [
        zone(100, 100, "Pine Lake National Park Of Canada", "National Park", (45.0, -80.0, 45.2, -79.8)),
        zone(200, 200, "Maple Provincial Park (Natural Environment Class)", "Provincial Park",
             (45.3, -80.0, 45.4, -79.9), owner=2, gov=2),
        zone(201, 200, "Maple Provincial Park Nature Reserve Zone", "Nature Reserve", (45.4, -80.0, 45.45, -79.9),  # noqa: E501
             owner=2, gov=2),
        zone(300, 300, "Owl Woods", "Privately Protected Area", (45.5, -80.0, 45.6, -79.9), owner=8, gov=8),
        zone(400, 400, "Valley Conservation Area", "Conservation Area", (45.6, -80.0, 45.7, -79.9), owner=8, gov=2),  # noqa: E501
        zone(500, 500, "Fen Land Trust Area", "Conservation Area", (45.7, -80.0, 45.8, -79.9), owner=8, gov=8),  # noqa: E501
        zone(600, 600, "Delisted Park", "Provincial Park", (45.8, -80.0, 45.9, -79.9), owner=2, gov=2, status=0),  # noqa: E501
        zone(700, 700, "Shore OECM", "National Park", (45.9, -80.0, 46.0, -79.9), pa=2),
        zone(800, 800, "Natural Area", "Municipal Park", (46.0, -80.0, 46.1, -79.9), owner=3, gov=3),
    ])  # fmt: skip


def usfs_shapefile(folder):
    folder.mkdir(parents=True, exist_ok=True)

    def ring(south, west, north, east):
        return [[(west, south), (west, north), (east, north), (east, south), (west, south)]]

    fields = [("FORESTORGC", "C", 8), ("FORESTNAME", "C", 80)]
    rows = [
        (ring(0.55, -139.95, 0.95, -139.55), ("0101", "North National Forest")),
        (ring(0.10, -139.95, 0.20, -139.85), ("0102", "Prairie National Grassland")),
        (ring(0.30, -139.95, 0.40, -139.85), ("0103", "Twin Rivers National Forests")),
    ]
    return write_shapefile(folder / "S_USA.AdministrativeForest", fields, rows, prj=NAD83_PRJ)


def wikidata_result(path, rows):
    """rows: (qid, name, lon, lat, area m² or None, country or None, sitelinks)."""
    bindings = []
    for qid, name, lon, lat, area, cc, links in rows:
        b = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"}, "name": {"value": name},
             "coord": {"value": f"Point({lon} {lat})"}, "sitelinks": {"value": str(links)}}  # fmt: skip
        if area is not None:
            b["area"] = {"value": str(area)}
        if cc is not None:
            b["cc"] = {"value": cc}
        bindings.append(b)
    path.write_text(json.dumps({"results": {"bindings": bindings}}))
    return path
