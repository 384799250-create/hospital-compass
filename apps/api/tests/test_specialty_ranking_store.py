import json

from app.specialty_ranking_store import import_ranking_records, ranking_records, initialize_ranking_store


def test_import_persists_and_deduplicates_ranking_records(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    initialize_ranking_store(db)
    rows = [
        {'hospital': '医院 A', 'city': '广州', 'specialty': '心血管内科', 'rank': '1', 'year': '2025', 'source': 'https://example.org/a'},
        {'hospital': '医院 A', 'city': '广州', 'specialty': '心血管内科', 'rank': '1', 'year': '2025', 'source': 'https://example.org/a'},
    ]
    assert import_ranking_records(rows, db) == 1
    records = ranking_records(hospital='医院 A', city='广州', specialty='心血管内科', path=db)
    assert len(records) == 1
    assert records[0]['verification_status'] == '待核验'
    assert records[0]['year'] == 2025


def test_import_accepts_json_payload(tmp_path):
    db = tmp_path / 'rankings.sqlite3'
    payload = json.dumps([{'hospital': '医院 B', 'city': '深圳', 'specialty': '肿瘤科', 'tier': '重点专科', 'year': 2024, 'source': 'https://example.org/b'}], ensure_ascii=False)
    assert import_ranking_records(json.loads(payload), db) == 1
    assert ranking_records(hospital='医院 B', path=db)[0]['tier'] == '重点专科'
