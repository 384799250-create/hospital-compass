import sqlite3

from app.data_cleaner import clean_database, normalize_location
from app.hospital_store import initialize


def test_normalize_location_fills_municipality_from_address():
    result = normalize_location('', '', '海淀区', '北京市海淀区复兴路28号')
    assert result == ('北京市', '北京市', '海淀区')


def test_normalize_location_extracts_province_city_district_from_address():
    result = normalize_location('', '', '', '广东省广州市越秀区中山二路106号')
    assert result == ('广东省', '广州市', '越秀区')


def test_clean_database_merges_only_exact_duplicate_identity(tmp_path):
    target = tmp_path / 'hospital.sqlite3'
    initialize(target)
    connection = sqlite3.connect(target)
    connection.executemany(
        'INSERT INTO hospitals (id,canonical_name,province,city,district,address,updated_at) VALUES (?,?,?,?,?,?,?)',
        [
            ('a', '测试医院', '广东省', '广州市', '越秀区', '广东省广州市越秀区1号', '2026-01-01'),
            ('b', '测试医院', '广东省', '广州市', '越秀区', '广东省广州市越秀区1号', '2026-01-01'),
            ('c', '测试医院', '广东省', '深圳市', '南山区', '广东省深圳市南山区2号', '2026-01-01'),
        ],
    )
    connection.commit()
    connection.close()

    report = clean_database(target, apply=True)

    assert report.merged_rows == 1
    connection = sqlite3.connect(target)
    assert connection.execute('SELECT COUNT(*) FROM hospitals').fetchone()[0] == 2
    connection.close()
