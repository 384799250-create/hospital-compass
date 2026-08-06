from datetime import date

from app.data import verified_row_to_hospital
from app.matcher import match


VERIFIED_BEIJING_ROW = {
    'id': 'beijing-pumch',
    'name': '北京协和医院',
    'city': 'Beijing',
    'tier': 'tertiary',
    'source_url': 'https://www.pumch.cn/front/',
    'source_date': '2026-08-06',
    'specialties': '心血管内科',
    'disease_tags': '冠心病',
    'verified': 'true',
    'published': 'true',
}


def test_verified_public_row_maps_only_source_backed_hospital_fields():
    hospital = verified_row_to_hospital(VERIFIED_BEIJING_ROW)

    assert hospital.id == 'beijing-pumch'
    assert hospital.name == '北京协和医院'
    assert hospital.pinyin_name == 'beijing-pumch'
    assert hospital.city == 'Beijing'
    assert hospital.specialties == ('心血管内科',)
    assert hospital.source_date == date(2026, 8, 6)
    assert hospital.published is True
    assert hospital.verified is True
    assert hospital.demo_label == '已核验公开信息'
    assert (hospital.specialty_score, hospital.capability_score, hospital.geography_score) == (None, None, None)


def test_explicit_hospital_collection_replaces_demo_fallback():
    response = match(
        '冠心病',
        'Beijing',
        'overall',
        hospitals=(verified_row_to_hospital(VERIFIED_BEIJING_ROW),),
        as_of=date(2026, 8, 6),
    )

    assert [result.id for result in response.results] == ['beijing-pumch']
