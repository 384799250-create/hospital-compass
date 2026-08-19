import json
from pathlib import Path

from app.hospital_store import connect, database_path, initialize, upsert_hospital, upsert_hospitals_bulk
from app.directory_import import split_address
from app.osm_importer import import_osm_hospitals
from app.geo_enricher import fill_cities_from_geojson


def test_database_defaults_to_f_drive(monkeypatch):
    monkeypatch.delenv('HOSPITAL_COMPASS_DATA_DIR', raising=False)
    assert database_path() == Path(r'F:\hospital-compass-data\hospital-compass.sqlite3')


def test_initialize_and_upsert_keep_structured_fields(tmp_path):
    target = tmp_path / 'directory.sqlite3'
    initialize(target)
    upsert_hospital({
        'id': 'gd-people',
        'name': '广东省人民医院',
        'province': '广东省', 'city': '广州市', 'district': '越秀区',
        'specialties': ['心血管内科'], 'aliases': ['广东人民医院'],
    }, [{'url': 'https://example.org/hospital', 'title': '医院官网'}], path=target)

    with connect(target) as connection:
        row = connection.execute('SELECT * FROM hospitals WHERE id = ?', ('gd-people',)).fetchone()
        source = connection.execute('SELECT source_url FROM hospital_sources WHERE hospital_id = ?', ('gd-people',)).fetchone()
    assert row['canonical_name'] == '广东省人民医院'
    assert json.loads(row['specialties_json']) == ['心血管内科']
    assert row['verification_status'] == '待核验'
    assert source['source_url'] == 'https://example.org/hospital'


def test_upsert_rejects_missing_identity(tmp_path):
    target = tmp_path / 'directory.sqlite3'
    initialize(target)
    try:
        upsert_hospital({'name': '缺少 ID'}, [], path=target)
    except ValueError as error:
        assert str(error) == 'hospital id and name are required'


def test_bulk_upsert_writes_all_records_and_sources_in_one_call(tmp_path):
    target = tmp_path / 'directory.sqlite3'
    initialize(target)
    count = upsert_hospitals_bulk([
        ({'id': 'bulk-1', 'name': '医院一'}, [{'source_url': 'file:///tmp/source.xlsx'}]),
        ({'id': 'bulk-2', 'name': '医院二'}, [{'source_url': 'file:///tmp/source.xlsx'}]),
    ], path=target)
    assert count == 2
    with connect(target) as connection:
        assert connection.execute('SELECT count(*) FROM hospitals').fetchone()[0] == 2
        assert connection.execute('SELECT count(*) FROM hospital_sources').fetchone()[0] == 2


def test_split_address_extracts_city_and_district():
    assert split_address('广东省广州市越秀区中山二路') == ('广东省', '广州市', '越秀区')
    assert split_address('北京市东城区朝内北小街2号') == ('北京市', '北京市', '东城区')


def test_import_osm_hospital_preserves_odbl_source(tmp_path):
    source = tmp_path / 'osm.json'
    source.write_text('{"osm3s":{"timestamp_osm_base":"2026-08-07T00:00:00Z"},"elements":[{"type":"node","id":1,"lat":23.1,"lon":113.3,"tags":{"name":"测试基层医院","addr:city":"广州市"}}]}', encoding='utf-8')
    target = tmp_path / 'directory.sqlite3'
    assert import_osm_hospitals(source, province='广东省', database_path=target) == 1
    with connect(target) as connection:
        row = connection.execute('SELECT * FROM hospitals').fetchone()
        source_row = connection.execute('SELECT source_type FROM hospital_sources').fetchone()
    assert row['canonical_name'] == '测试基层医院'
    assert source_row['source_type'] == 'OpenStreetMap（ODbL）'


def test_fill_cities_uses_polygon_boundaries(tmp_path):
    target = tmp_path / 'directory.sqlite3'
    initialize(target)
    upsert_hospital({'id': 'geo-1', 'name': '空间医院', 'province': '广东省', 'longitude': 1, 'latitude': 1}, path=target)
    boundary = tmp_path / 'bound.json'
    boundary.write_text('{"features":[{"properties":{"name":"测试市"},"geometry":{"type":"Polygon","coordinates":[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}}]}', encoding='utf-8')

    assert fill_cities_from_geojson(boundary, province='广东省', database_path=target) == 1
    with connect(target) as connection:
        assert connection.execute('SELECT city FROM hospitals WHERE id = ?', ('geo-1',)).fetchone()['city'] == '测试市'
