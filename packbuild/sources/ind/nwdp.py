"""Survey of India state and district boundaries as the National Water Data Portal publishes them:
the `states` and `districts` polygon layers. NOT IN ANY PACK YET: the licence is not cleared.

The portal (nwdp.nwic.gov.in, datasets "State Boundary" and "District Boundary") offers the Survey
of India's Administrative Boundary data without an account, as SHP, GeoJSON and KMZ. Its licence
field says only "Other (Open)", and its copyright policy allows reproduction with acknowledgement
except for material that is a third party's copyright, which this Survey of India data may be; the
Survey of India's own portal allows its boundary files for consultative, research and education
use. Until that is resolved there is no registry file for SOURCE, and packbuild.india refuses to
build these layers.

Format (checked on the May 2025 files): attributes id, objectid, state (two letters: ISO 3166-2
except "LK" for Ladakh), stcode (LGD state code: 36 Telangana, 37 Ladakh and 38 Dadra and Nagar
Haveli and Daman and Diu exist only in LGD), state_name, plus district and dtcode (LGD district
code) in the district file. The SHP and GeoJSON are projected, WGS 84 / India NSF LCC (EPSG:7755,
metres), so they are refused here; only a WGS84 longitude/latitude file (GeoJSON without a
projected "crs", or a shapefile whose .prj is geographic WGS84) is read. The boundaries are the
Survey of India's and show India's official view of its borders, including areas India claims that
other countries administer: the state file's own shape_area gives Ladakh 169,463 km2 and Jammu and
Kashmir 52,770 km2, against about 59,000 and 42,000 km2 administered by India.

Ids: states "iso:IN-XX", the same ids the world pack's admin1 layer uses, so India-pack states and
world-pack states line up (except where Natural Earth still has the pre-2023 codes IN-CT, IN-OR,
IN-TG and IN-UT); the LGD code is kept as a column. Districts "lgd:<dtcode>".
"""

from pathlib import Path

from placewise.io import read_shapefile
from placewise.model import Feature

from ...layer import LayerData
from ._common import ISO_NAMES, read_wgs84_geojson, text

SOURCE = "nwdp-soi-boundaries"
_PORTAL_CODES = {"LK": "LA"}  # the portal's own code -> ISO 3166-2 suffix


def states(path):
    raw = _read(path)
    props = [f.properties for f in raw]
    iso = [_iso(p) for p in props]
    columns = {
        "id": [f"iso:{c}" for c in iso],
        "name": [ISO_NAMES[c] for c in iso],
        "iso": iso,
        "lgd": [text(p.get("stcode")) for p in props],
        "source_name": [text(p.get("state_name")) for p in props],
    }
    return _layer("states", columns, raw)


def districts(path):
    raw = _read(path)
    props = [f.properties for f in raw]
    columns = {
        "id": [f"lgd:{text(p.get('dtcode'))}" for p in props],
        "name": [text(p.get("district")) for p in props],
        "lgd": [text(p.get("dtcode")) for p in props],
        "state_code": [_iso(p) for p in props],
        "state_lgd": [text(p.get("stcode")) for p in props],
        "state": [text(p.get("state_name")) for p in props],
    }
    return _layer("districts", columns, raw)


def _read(path):
    path = Path(path)
    return read_shapefile(path) if path.suffix.lower() == ".shp" else read_wgs84_geojson(path)


def _iso(props):
    code = text(props.get("state")).upper()
    iso = f"IN-{_PORTAL_CODES.get(code, code)}"
    if iso not in ISO_NAMES:
        raise ValueError(f"unknown state code {code!r} (state_name {text(props.get('state_name'))!r})")
    return iso


def _layer(name, columns, raw):
    features = [Feature(f.outlines, {}, fid) for f, fid in zip(raw, columns["id"], strict=True)]
    types = {c: "str" for c in columns}
    return LayerData(name, "polygon", columns, (SOURCE,), features=features, types=types)
