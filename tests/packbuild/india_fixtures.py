"""Tiny India fixtures in each source's exact format, written at test time (nothing to commit).

Shapes are coarse boxes round public landmarks (MG Road in Bengaluru, the Gateway of India, the
Charminar, India Gate), not real boundaries; post office rows name public post offices with
approximate coordinates. Formats:

- All India Pincode Boundary: one GeoJSON FeatureCollection, CRS84, properties Pincode,
  Office_Name, Division, Region, Circle with the trailing spaces the real file has.
- All India Pincode Directory: the data.gov.in CSV download, every field quoted.
- Survey of India state and district boundaries as the National Water Data Portal publishes them
  (fields id, objectid, state, stcode, [district, dtcode,] ds_name, src_agency, state_name), here
  in WGS84; the real files are projected (EPSG:7755).
"""

import csv
import json

import shapefile  # pyshp

WGS84_PRJ = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
NSF_LCC_PRJ = (
    'PROJCS["WGS_1984_India_NSF_LCC",GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],PRIMEM["Greenwich",0.0],'
    'UNIT["Degree",0.0174532925199433]],PROJECTION["Lambert_Conformal_Conic"],'
    'PARAMETER["False_Easting",4000000.0],PARAMETER["False_Northing",4000000.0],'
    'PARAMETER["Central_Meridian",80.0],PARAMETER["Standard_Parallel_1",12.472955],'
    'PARAMETER["Standard_Parallel_2",35.1728044444444],PARAMETER["Latitude_Of_Origin",24.0],'
    'UNIT["Meter",1.0]]'
)

# landmarks the spot checks use: (lat, lon)
MG_ROAD = (12.9756, 77.6060)
GATEWAY_OF_INDIA = (18.9220, 72.8347)
CHARMINAR = (17.3616, 78.4747)
INDIA_GATE = (28.6129, 77.2295)


def ring(south, west, north, east):
    """A closed counter-clockwise GeoJSON ring of (lon, lat) positions."""
    return [[west, south], [east, south], [east, north], [west, north], [west, south]]


def _feature(props, geometry):
    return {"type": "Feature", "properties": props, "geometry": geometry}


def _pin(pincode, office, division, region, circle):
    return {
        "Pincode": pincode,
        "Office_Name": office,
        "Division": division,
        "Region": region,
        "Circle": circle,
    }


def boundary_features():
    poly = lambda *box: {"type": "Polygon", "coordinates": [ring(*box)]}  # noqa: E731
    return [
        _feature(
            _pin("560001", "Bengaluru G.P.O.", "BENGALURU GPO ", "Bengaluru HQ ", "Karnataka "),
            poly(12.95, 77.58, 13.00, 77.63),
        ),
        _feature(
            _pin("400001", "Mumbai G.P.O.", "Mumbai GPO ", "Mumbai HQ ", "Maharashtra "),
            {
                "type": "MultiPolygon",
                "coordinates": [[ring(18.90, 72.82, 18.95, 72.85)], [ring(18.96, 72.82, 18.97, 72.83)]],
            },
        ),
        # no PIN code: dropped
        _feature(_pin("", "", "", "", ""), poly(15.0, 75.0, 15.1, 75.1)),
        _feature(
            _pin("500002", "Charminar S.O", "Hyderabad City ", "Hyderabad HQ ", "Telangana "),
            poly(17.35, 78.46, 17.37, 78.49),
        ),
        # a second polygon for 560001: merged into the first feature
        _feature(
            _pin("560001", "Bengaluru G.P.O.", "BENGALURU GPO ", "Bengaluru HQ ", "Karnataka "),
            poly(13.01, 77.58, 13.02, 77.59),
        ),
        _feature(
            _pin("110001", "New Delhi GPO", "New Delhi GPO ", "", "Delhi "), poly(28.60, 77.19, 28.64, 77.24)
        ),
        # a PIN code the directory doesn't list: no district or state
        _feature(_pin("194101", "Leh H.O", "Leh ", "", "Jammu & Kashmir "), poly(34.10, 77.50, 34.20, 77.65)),
    ]


def write_boundaries(path, features=None):
    data = {
        "type": "FeatureCollection",
        "name": "All_India_pincode_Boundary-cleaned",
        "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:OGC:1.3:CRS84"}},
        "features": boundary_features() if features is None else features,
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


DIRECTORY_HEADER = (
    "CircleName", "RegionName", "DivisionName", "OfficeName", "Pincode", "OfficeType", "Delivery",
    "District", "StateName", "Latitude", "Longitude",
)  # fmt: skip


def directory_rows():
    ka = ("Karnataka Circle", "Bengaluru HQ Region", "Bengaluru GPO Division")
    mh = ("Maharashtra Circle", "Mumbai HQ Region", "Mumbai GPO Division")
    ts = ("Telangana Circle", "Hyderabad HQ Region", "Hyderabad City Division")
    dl = ("Delhi Circle", "", "New Delhi GPO Division")
    blr, mum, dlh = ("BENGALURU URBAN", "KARNATAKA"), ("MUMBAI", "MAHARASHTRA"), ("NEW DELHI", "DELHI")
    rural = ("BENGALURU RURAL", "KARNATAKA")
    return [
        (*ka, "Bengaluru G.P.O.", "560001", "HO", "Delivery", *blr, "12.9839", "77.5929"),
        (*ka, "Vidhana Soudha S.O", "560001", "PO", "Non Delivery", *blr, "12.9791", "77.5913"),
        # an office of the same PIN code filed under another district: the majority wins
        (*ka, "Rajbhavan S.O", "560001", "PO", "Non Delivery", *rural, "12.9850", "77.5900"),
        (*mh, "Mumbai G.P.O.", "400001", "HO", "Delivery", *mum, "18.9398", "72.8355"),
        # unusable coordinates: kept for the join, left out of post_offices
        (*mh, "Town Hall S.O", "400001", "PO", "Non Delivery", *mum, "NA", "NA"),
        (*mh, "Bazargate S.O", "400001", "PO", "Delivery", *mum, "1.0000000", "1.0000000"),
        (*mh, "Stock Exchange S.O", "400001", "PO", "Non Delivery", *mum, "18.9300", "72.8338-"),
        (*ts, "Charminar S.O", "500002", "PO", "Delivery", "HYDERABAD", "TELANGANA", "17.3616", "78.4747"),
        # an exact duplicate row: kept once
        (*ts, "Charminar S.O", "500002", "PO", "Delivery", "HYDERABAD", "TELANGANA", "17.3616", "78.4747"),
        (*dl, "New Delhi G.P.O.", "110001", "HO", "Delivery", *dlh, "28.6250", "77.2140"),
        # the same office name and PIN code twice with different details: both kept, ids made unique
        (*dl, "Parliament House S.O", "110001", "PO", "Non Delivery", *dlh, "28.6172", "77.2082"),
        (*dl, "Parliament House S.O", "110001", "PO", "Delivery", *dlh, "28.6175", "77.2085"),
        ("Maharashtra Circle", "Goa Region", "Valsad Division", "Silvassa S.O", "396230", "PO", "Delivery",
         "DADRA AND NAGAR HAVELI", "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU", "20.2740", "73.0120"),
    ]  # fmt: skip


def write_directory(path, rows=None, header=DIRECTORY_HEADER):
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL)
        w.writerow(header)
        w.writerows(directory_rows() if rows is None else rows)
    return path


def _nwdp_state(i, code, lgd, name):
    return {
        "id": i, "objectid": i, "state": code, "stcode": lgd, "shape_length": 1.0, "shape_area": 1.0,
        "ds_name": " Administrative Boundary", "src_agency": "Survey of India (SOI)", "state_name": name,
    }  # fmt: skip


NWDP_STATES = [
    (_nwdp_state(16, "KA", "29", "Karnataka"), (11.5, 74.0, 18.5, 78.6)),
    (_nwdp_state(20, "MH", "27", "Maharashtra"), (15.6, 72.6, 22.1, 80.9)),
    (_nwdp_state(33, "TS", "36", "Telangana"), (15.8, 77.2, 19.95, 81.3)),
    (_nwdp_state(9, "DL", "07", "Delhi"), (28.4, 76.8, 28.9, 77.35)),
    # the portal writes "LK" for Ladakh, whose ISO 3166-2 code is IN-LA
    (_nwdp_state(19, "LK", "37", "Ladakh"), (32.3, 75.3, 35.7, 80.3)),
    (_nwdp_state(3, "AR", "12", "Arunanchal Pradesh"), (26.6, 91.5, 29.5, 97.4)),
]
NWDP_DISTRICTS = [
    ({**_nwdp_state(150, "KA", "29", "Karnataka"), "district": "Bengaluru Urban", "dtcode": "572"},
     (12.80, 77.40, 13.15, 77.80)),
    ({**_nwdp_state(300, "MH", "27", "Maharashtra"), "district": "Mumbai", "dtcode": "482"},
     (18.89, 72.79, 19.00, 72.87)),
    ({**_nwdp_state(377, "MN", "14", "Manipur"), "district": "Kamjong", "dtcode": "717"},
     (24.70, 94.30, 25.40, 94.75)),
]  # fmt: skip


def write_nwdp_geojson(path, rows, crs="urn:ogc:def:crs:OGC:1.3:CRS84"):
    features = [
        _feature(props, {"type": "MultiPolygon", "coordinates": [[ring(*box)]]}) for props, box in rows
    ]
    data = {"type": "FeatureCollection", "name": path.stem, "features": features}
    if crs:
        data["crs"] = {"type": "name", "properties": {"name": crs}}
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def write_nwdp_shapefile(base, rows, prj=WGS84_PRJ):
    """A shapefile with the portal's attribute table (a clockwise outer ring per feature)."""
    names = list(rows[0][0])
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON, encoding="utf-8") as w:
        for name in names:
            if name in ("id", "objectid"):
                w.field(name, "N", 10, 0)
            elif name in ("shape_length", "shape_area"):
                w.field(name[:10], "N", 24, 15)
            else:
                w.field(name, "C", 254)
        for props, box in rows:
            w.poly([list(reversed(ring(*box)))])
            w.record(*[props[n] for n in names])
    base.with_suffix(".prj").write_text(prj)
    base.with_suffix(".cpg").write_text("UTF-8")
    return base.with_suffix(".shp")
