"""Statistics Canada boundary files and population tables into the Canada pack's layers."""

import json
from pathlib import Path

import pytest
import statcan_fixtures as fx

from packbuild.sources import statcan

POP = statcan.read_population(*fx.POPULATION.values())


def _col(layer, name):
    return list(layer.columns[name])


def _where(layer, lat, lon):
    """Ids of the features containing a point, in layer order."""
    return [f.id for f in layer.features if f.contains(lat, lon)]


@pytest.fixture
def files(tmp_path):
    return {stem: fx.write_shapefile(tmp_path, stem) for stem in fx.LAYERS}


# --- population ---------------------------------------------------------------------------------


def test_read_population_keys_every_table_by_dguid():
    assert POP["2021A000011124"] == 36991981  # Canada, in all three tables
    assert POP["2021A000235"] == 14223942  # Ontario
    assert POP["2021A00033524"] == 596637  # Halton (CD)
    assert POP["2021A00053524009"] == 132979  # Milton (CSD)
    assert POP["2021S0503535"] == 6202225  # Toronto CMA
    assert POP["2021S0504828"] == 15990  # Canmore CA
    assert POP["2021S050535505"] == 1135014  # Ottawa - Gatineau, Ontario part
    assert POP["2021A0011M5J"] == 16879  # FSA, from the table with the shorter header
    assert POP["2021A00052406804"] is None  # Listuguj: suppressed (".."), not zero


def test_read_population_refuses_a_table_without_a_2021_population_column(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text('"REF_DATE","GEO","DGUID","Coordinate","Something else"\n"2021","Canada","x","1","5"\n')
    with pytest.raises(ValueError, match="Population, 2021"):
        statcan.read_population(bad)


# --- codes --------------------------------------------------------------------------------------


def test_province_codes_cover_the_13_provinces_and_territories():
    assert statcan.PROVINCE_CODES == {
        "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON", "46": "MB",
        "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU",
    }  # fmt: skip


def test_dguids_follow_the_2021_schemas():
    assert statcan.dguid("csd", "3520005") == "2021A00053520005"
    assert statcan.dguid("cd", "3520") == "2021A00033520"
    assert statcan.dguid("pr", "35") == "2021A000235"
    assert statcan.dguid("fsa", "M5V") == "2021A0011M5V"
    assert statcan.dguid("cma", "535") == "2021S0503535"  # a CMA (type B) ...
    assert statcan.dguid("ca", "828") == "2021S0504828"  # ... and a CA use different schemas


# --- layers -------------------------------------------------------------------------------------


def test_provinces(files):
    layer = statcan.provinces(files["lpr_000b21a_e"], POP)
    assert (layer.name, layer.kind) == ("provinces", "polygon")
    assert layer.sources == (statcan.BOUNDARIES, statcan.POPULATION)
    assert _col(layer, "id") == ["statcan:35", "statcan:24", "statcan:48"]
    assert _col(layer, "name") == ["Ontario", "Quebec", "Alberta"]  # English, not "Quebec / Québec"
    assert _col(layer, "name_fr") == ["Ontario", "Québec", "Alberta"]
    assert _col(layer, "code") == ["ON", "QC", "AB"]
    assert _col(layer, "pruid") == ["35", "24", "48"]
    assert _col(layer, "population") == [14223942, 8501833, 4262635]
    assert layer.types["population"] == "i8" and layer.nulls == {"population": -1}
    assert set(layer.types) == set(layer.columns)
    assert _where(layer, *fx.PARLIAMENT_HILL) == ["statcan:35"]
    assert _where(layer, *fx.GATINEAU) == ["statcan:24"]


def test_census_subdivisions(files):
    layer = statcan.census_subdivisions(files["lcsd000b21a_e"], POP)
    assert layer.name == "csd"
    assert _col(layer, "id")[:3] == ["statcan:3520005", "statcan:3521005", "statcan:3524009"]
    names = dict(zip(_col(layer, "id"), _col(layer, "name"), strict=True))
    assert names["statcan:4815032"] == "Improvement District No. 9 Banff"  # StatCan's double space folded
    assert _col(layer, "csdtype") == ["C", "CY", "T", "CV", "V", "ID", "T", "IRI"]
    assert _col(layer, "province") == ["ON", "ON", "ON", "ON", "QC", "AB", "AB", "QC"]
    assert _col(layer, "cduid") == ["3520", "3521", "3524", "3506", "2481", "4815", "4815", "2406"]
    pop = dict(zip(_col(layer, "id"), _col(layer, "population"), strict=True))
    assert pop["statcan:3520005"] == 2794356 and pop["statcan:3524009"] == 132979
    assert pop["statcan:2406804"] is None  # suppressed in the census table
    assert _where(layer, *fx.CN_TOWER) == ["statcan:3520005"]
    assert _where(layer, *fx.MISSISSAUGA) == ["statcan:3521005"]
    assert _where(layer, *fx.MILTON_GO) == ["statcan:3524009"]
    assert _where(layer, *fx.PARLIAMENT_HILL) == ["statcan:3506008"]
    assert _where(layer, *fx.GATINEAU) == ["statcan:2481017"]
    assert _where(layer, *fx.LAKE_LOUISE) == ["statcan:4815032"]
    assert _where(layer, *fx.BANFF) == ["statcan:4815035"]  # the town is a hole in the national park


def test_csd_rings_are_simplified_in_metres(files):
    simplified = statcan.census_subdivisions(files["lcsd000b21a_e"], tolerance_m=10)
    toronto = simplified.features[0]
    assert [len(r) for o in toronto.outlines for r in o.rings] == [4]  # 200 collinear points, 3 m island
    raw = statcan.census_subdivisions(files["lcsd000b21a_e"], tolerance_m=0)
    assert [len(r) for o in raw.features[0].outlines for r in o.rings] == [200, 3]


def test_without_population_the_column_is_null_and_the_table_is_not_credited(files):
    layer = statcan.census_subdivisions(files["lcsd000b21a_e"])
    assert layer.sources == (statcan.BOUNDARIES,)
    assert set(_col(layer, "population")) == {None}


def test_census_divisions(files):
    layer = statcan.census_divisions(files["lcd_000b21a_e"], POP)
    assert layer.name == "cd"
    assert _col(layer, "id") == [f"statcan:{c}" for c in ("3520", "3521", "3524", "3506", "2481", "4815")]
    assert _col(layer, "name")[:3] == ["Toronto", "Peel", "Halton"]
    assert _col(layer, "cdtype") == ["CDR", "RM", "RM", "CDR", "TÉ", "CDR"]
    assert _col(layer, "province") == ["ON", "ON", "ON", "ON", "QC", "AB"]
    assert _col(layer, "population")[2] == 596637
    assert _where(layer, *fx.MILTON_GO) == ["statcan:3524"]
    assert _where(layer, *fx.MISSISSAUGA) == ["statcan:3521"]


def test_metro_areas(files):
    layer = statcan.metro_areas(files["lcma000b21a_e"], POP)
    assert layer.name == "cma"
    assert _col(layer, "id") == ["statcan:35535", "statcan:35505", "statcan:24505", "statcan:48828"]
    # both parts of a CMA that crosses a provincial border carry its plain name and whole population
    assert _col(layer, "name") == ["Toronto", "Ottawa - Gatineau", "Ottawa - Gatineau", "Canmore"]
    assert _col(layer, "name_full")[1] == "Ottawa - Gatineau (Ontario part / partie de l'Ontario)"
    assert _col(layer, "cmauid") == ["535", "505", "505", "828"]
    assert _col(layer, "cmatype") == ["B", "B", "B", "D"]
    assert _col(layer, "kind") == ["CMA", "CMA", "CMA", "CA"]
    assert _col(layer, "province") == ["ON", "ON", "QC", "AB"]
    assert _col(layer, "population") == [6202225, 1488307, 1488307, 15990]
    assert _where(layer, *fx.MILTON_GO) == ["statcan:35535"]
    assert _where(layer, *fx.GATINEAU) == ["statcan:24505"]
    assert _where(layer, *fx.LAKE_LOUISE) == []


def test_forward_sortation_areas(files):
    layer = statcan.forward_sortation_areas(files["lfsa000b21a_e"], POP)
    assert layer.name == "fsa"
    assert layer.sources == (statcan.FSA, statcan.POPULATION)
    assert _col(layer, "id")[:2] == ["statcan:M5J", "statcan:L9T"]
    assert _col(layer, "name")[:2] == ["M5J", "L9T"]
    assert _col(layer, "province") == ["ON", "ON", "ON", "QC", "AB", "AB"]
    assert _col(layer, "population")[0] == 16879
    assert _where(layer, *fx.CN_TOWER) == ["statcan:M5J"]
    assert _where(layer, *fx.LAKE_LOUISE) == ["statcan:T0L"]


def test_service_pages_read_like_the_shapefile(tmp_path, files):
    pages, _ = fx.service_pages("lcsd000b21a_e")
    folder = tmp_path / "lcsd000b21s_e"
    folder.mkdir()
    for i, page in enumerate(pages):
        (folder / f"page-{i:04d}.json").write_text(page)
    from_service = statcan.census_subdivisions(folder, POP)
    from_files = statcan.census_subdivisions(files["lcsd000b21a_e"], POP)
    assert from_service.columns == from_files.columns
    assert _where(from_service, *fx.BANFF) == ["statcan:4815035"]


# --- input checks -------------------------------------------------------------------------------


def test_a_shapefile_without_a_prj_is_refused(tmp_path):
    shp = fx.write_shapefile(tmp_path, "lpr_000b21a_e", prj=None)
    with pytest.raises(ValueError, match=r"\.prj"):
        statcan.provinces(shp)


def test_a_shapefile_in_another_projection_is_refused(tmp_path):
    wgs84 = 'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",SPHEROID["WGS_1984",6378137.0,298.257223563]]]'
    with pytest.raises(ValueError, match="Lambert"):
        statcan.provinces(fx.write_shapefile(tmp_path / "a", "lpr_000b21a_e", prj=wgs84))
    utm = fx.STATCAN_PRJ.replace('"Standard_Parallel_1",49.0', '"Standard_Parallel_1",50.0')
    with pytest.raises(ValueError, match="Standard_Parallel_1"):
        statcan.provinces(fx.write_shapefile(tmp_path / "b", "lpr_000b21a_e", prj=utm))


def test_service_pages_in_another_spatial_reference_are_refused(tmp_path):
    folder = tmp_path / "lpr_000b21s_e"
    folder.mkdir()
    pages, _ = fx.service_pages("lpr_000b21a_e")
    page = json.loads(pages[0])
    page["spatialReference"] = {"wkid": 4326, "latestWkid": 4326}
    (folder / "page-0000.json").write_text(json.dumps(page))
    with pytest.raises(ValueError, match="3347"):
        statcan.provinces(folder)


def test_an_unknown_province_uid_is_an_error(tmp_path):
    import shapefile

    base = tmp_path / "odd"
    with shapefile.Writer(str(base), shapeType=shapefile.POLYGON) as w:
        for field in fx.PR_FIELDS:
            w.field(*field)
        w.poly([fx.lambert(fx.box(45, -80, 46, -79))])
        w.record("99", "2021A000299", "Nowhere", "Nowhere", "Nulle part", "N.", "N.", 1.0)
    Path(f"{base}.prj").write_text(fx.STATCAN_PRJ)
    with pytest.raises(ValueError, match="99"):
        statcan.provinces(Path(f"{base}.shp"))
