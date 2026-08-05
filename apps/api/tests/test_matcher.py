from dataclasses import replace
from datetime import date, timedelta

import app.matcher as matcher
from app.data import DEMO_HOSPITALS
from app.matcher import match
import pytest


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

    assert response.results[0].score == 9.4444


@pytest.mark.parametrize('source_date', [None, 'not-a-date', date.today() + timedelta(days=1)])
def test_missing_invalid_or_future_source_is_ineligible(monkeypatch, source_date):
    hospital = replace(DEMO_HOSPITALS[0], source_date=source_date)
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (hospital,))

    assert match('冠心病', '上海', 'overall').results == []


@pytest.mark.parametrize(
    ('change', 'value'),
    [
        ('published', False),
        ('verified', False),
        ('source_date', date.today() - timedelta(days=181)),
    ],
)
def test_unpublished_unverified_or_expired_hospital_is_excluded(monkeypatch, change, value):
    hospital = replace(DEMO_HOSPITALS[0], **{change: value})
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (hospital,))

    assert match('冠心病', '上海', 'overall').results == []


@pytest.mark.parametrize(
    ('priority', 'expected'),
    [
        ('overall', (57, 33, 0, 10)),
        ('specialty', (72, 28, 0, 10)),
        ('convenience', (47, 28, 0, 10)),
    ],
)
def test_no_city_redistributes_geography_for_every_priority(priority, expected):
    assert matcher._weights_for(priority, None) == expected


def test_equally_scored_hospitals_tie_break_by_freshness_then_pinyin(monkeypatch):
    fresher = replace(DEMO_HOSPITALS[0], name='示例新医院', pinyin_name='z', source_date=date.today() - timedelta(days=10))
    older = replace(
        DEMO_HOSPITALS[0],
        name='示例旧医院',
        pinyin_name='a',
        capability_score=92.2222222222,
        source_date=date.today() - timedelta(days=20),
    )
    same_freshness_earlier_name = replace(DEMO_HOSPITALS[0], name='示例甲医院', pinyin_name='a', source_date=date.today() - timedelta(days=10))
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (fresher, older, same_freshness_earlier_name))

    response = match('未知查询', '上海', 'overall')

    assert [result.name for result in response.results] == ['示例甲医院', '示例新医院', '示例旧医院']
