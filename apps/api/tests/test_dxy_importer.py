from app.dxy_importer import parse_hospital_list


def test_parse_dxy_hospital_rows():
    html = '''
    <div class="tr">
      <div class="td"><div class="hospital-title"><a href="/hospital/42">示例医院</a></div></div>
      <div class="td">广东·深圳市</div>
      <div class="td">公立医院</div>
      <div class="td">综合医院</div>
      <div class="td">三级甲等</div>
      <div class="td">1000 人以上</div>
      <div class="td">1980 年</div>
    </div>'''

    rows = parse_hospital_list(html)

    assert rows == [{
        'id': 'dxy-42',
        'name': '示例医院',
        'province': '广东省',
        'city': '深圳市',
        'address': '',
        'tier': '三级甲等',
        'nature': '公立医院',
        'hospital_type': '综合医院',
        'source_url': 'https://y.dxy.cn/hospital/42',
    }]
