from dataclasses import replace

import app.matcher as matcher
from app.data import DEMO_HOSPITALS
from app.matcher import match


def test_emergency_query_has_no_results():
    response = match('突发胸痛并呼吸困难', None, 'overall')

    assert response.emergency is True
    assert response.results == []


def test_specialty_sort_is_deterministic():
    response = match('冠心病', '上海', 'specialty')

    assert response.directions == ['心血管内科']
    assert response.results[0].name == '示例市中心医院'


def test_missing_score_fields_contribute_zero(monkeypatch):
    incomplete = replace(
        DEMO_HOSPITALS[0],
        specialty_score=None,
        capability_score=None,
        geography_score=None,
    )
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (incomplete,))

    response = match('冠心病', '上海', 'overall')

    assert response.results[0].score > 0
