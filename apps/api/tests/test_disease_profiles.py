from app.disease_profiles import has_explicit_disease, matched_explicit_disease_terms, profile_for_query


def test_cardiovascular_profile_maps_symptoms_to_core_departments():
    profile = profile_for_query('\u5fc3\u7ede\u75db')

    assert profile.key == 'cardiovascular'
    assert '\u5fc3\u8840\u7ba1\u5185\u79d1' in profile.departments
    assert '\u80f8\u75db\u4e2d\u5fc3' in profile.departments
    assert '\u51a0\u5fc3\u75c5' in profile.keywords


def test_unknown_query_keeps_generic_profile_without_inventing_specialty():
    profile = profile_for_query('\u4e00\u4e2a\u65e0\u6cd5\u8bc6\u522b\u7684\u75c7\u72b6')

    assert profile.key == 'general'
    assert profile.departments == ()
    assert profile.keywords == ()


def test_explicit_disease_detection_distinguishes_disease_names_from_symptoms():
    assert has_explicit_disease('我已经确诊糖尿病，想找医院') is True
    assert has_explicit_disease('胸痛两天了') is False


def test_matched_explicit_disease_terms_only_returns_the_terms_present_in_query():
    assert matched_explicit_disease_terms('脑溢血') == ('脑溢血',)
    assert matched_explicit_disease_terms('确诊脑出血') == ('脑出血',)
    assert matched_explicit_disease_terms('脑溢血和渐冻症') == ('脑溢血', '渐冻症')
    assert matched_explicit_disease_terms('胸痛两天了') == ()


def test_neurology_aliases_are_treated_as_one_explicit_disease():
    for query in ('渐冻症', '肌萎缩侧索硬化', 'ALS', '运动神经元病'):
        assert profile_for_query(query).key == 'neurology'
        assert has_explicit_disease(query) is True


def test_common_aliases_map_to_their_system_profile():
    assert profile_for_query('糖尿病').key == 'diabetes'
    assert profile_for_query('腰椎间盘突出').key == 'orthopedics'
    assert profile_for_query('慢阻肺 COPD').key == 'respiratory'
    assert profile_for_query('胃食管反流 GERD').key == 'digestive'
    assert profile_for_query('甲亢').key == 'endocrine'
    assert profile_for_query('帕金森病').key == 'neurology'


def test_negated_disease_and_symptom_text_do_not_become_explicit_diseases():
    assert has_explicit_disease('没有糖尿病') is False
    assert has_explicit_disease('排除脑梗死') is False
    assert has_explicit_disease('不是帕金森病') is False
    assert profile_for_query('手脚无力、头晕').key == 'general'


def test_short_english_abbreviations_require_token_boundaries():
    assert has_explicit_disease('AD') is True
    assert has_explicit_disease('ad hoc 广告文案') is False
    assert has_explicit_disease('MS office 文件') is False
