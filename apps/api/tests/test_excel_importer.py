from app.excel_importer import record_from_row


def test_record_from_medical_insurance_row_maps_public_fields_only():
    record = record_from_row((
        '广东省', '深圳市', '示例医院', '广东省深圳市南山区示例路1号',
        '0755-123456', '三级甲等', '心内科|呼吸科', '公立',
        'private@example.org', 'https://hospital.example.org',
    ))

    assert record['name'] == '示例医院'
    assert record['province'] == '广东省'
    assert record['city'] == '深圳市'
    assert record['district'] == '南山区'
    assert record['address'] == '广东省深圳市南山区示例路1号'
    assert record['tier'] == '三级甲等'
    assert record['nature'] == '公立'
    assert record['specialties'] == ['心内科', '呼吸科']
    assert record['official_domain'] == 'hospital.example.org'
    assert 'phone' not in record
    assert 'email' not in record
