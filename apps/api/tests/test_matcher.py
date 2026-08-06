from dataclasses import replace
from datetime import date, timedelta

import app.matcher as matcher
from app.data import DEMO_HOSPITALS
from app.matcher import match
import pytest

AS_OF = date(2026, 8, 5)


def test_emergency_query_has_no_results():
    response = match('突发胸痛并呼吸困难', None, 'overall', as_of=AS_OF)

    assert response.emergency is True
    assert response.results == []


def test_specialty_sort_is_deterministic():
    response = match('冠心病', '上海', 'specialty', as_of=AS_OF)

    assert response.directions == ['心血管内科']
    assert response.results[0].name == '示例市中心医院'


def test_unknown_query_returns_no_directions_and_no_results():
    response = match('无法映射的查询', '上海', 'overall', as_of=AS_OF)

    assert response.directions == []
    assert response.results == []


@pytest.mark.parametrize(
    ('query', 'direction'),
    [
        ('眼睛疼', '眼科'),
        ('视物模糊', '眼科'),
        ('红眼', '眼科'),
        ('鼻塞', '耳鼻咽喉头颈外科'),
        ('耳痛', '耳鼻咽喉头颈外科'),
        ('听力下降', '耳鼻咽喉头颈外科'),
        ('咽痛', '耳鼻咽喉头颈外科'),
    ],
)
def test_tongren_symptoms_map_to_their_clinical_direction(query, direction):
    response = match(query, '北京', 'overall', as_of=AS_OF)

    assert response.directions == [direction]


def test_recognized_direction_excludes_hospitals_without_that_specialty(monkeypatch):
    unrelated = replace(
        DEMO_HOSPITALS[0],
        id='demo-unrelated',
        name='示例无关医院',
        specialties=('神经内科',),
        specialty_score=100,
    )
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (unrelated, DEMO_HOSPITALS[0]))

    response = match('冠心病', '上海', 'specialty', as_of=AS_OF)

    assert [result.id for result in response.results] == ['demo-1']


def test_fixed_fixture_expires_against_an_injected_future_date():
    response = match('冠心病', '上海', 'overall', as_of=date(2027, 1, 23))

    assert response.results == []


def test_match_results_include_card_metadata():
    response = match('冠心病', '上海', 'specialty', as_of=AS_OF)
    result = response.results[0]

    assert result.specialties == ['心血管内科']
    assert result.score_reasons == ['专科方向匹配', '服务能力信息', '同城信息', '来源信息在有效期内']
    assert result.source_date == DEMO_HOSPITALS[0].source_date


def test_missing_score_fields_contribute_zero(monkeypatch):
    incomplete = replace(
        DEMO_HOSPITALS[0],
        specialty_score=None,
        capability_score=None,
        geography_score=None,
    )
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (incomplete,))

    response = match('冠心病', '上海', 'overall', as_of=AS_OF)

    assert response.results[0].score == 9.4444


@pytest.mark.parametrize('source_date', [None, 'not-a-date', AS_OF + timedelta(days=1)])
def test_missing_invalid_or_future_source_is_ineligible(monkeypatch, source_date):
    hospital = replace(DEMO_HOSPITALS[0], source_date=source_date)
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (hospital,))

    assert match('冠心病', '上海', 'overall', as_of=AS_OF).results == []


@pytest.mark.parametrize(
    ('change', 'value'),
    [
        ('published', False),
        ('verified', False),
        ('source_date', AS_OF - timedelta(days=181)),
    ],
)
def test_unpublished_unverified_or_expired_hospital_is_excluded(monkeypatch, change, value):
    hospital = replace(DEMO_HOSPITALS[0], **{change: value})
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (hospital,))

    assert match('冠心病', '上海', 'overall', as_of=AS_OF).results == []


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
    fresher = replace(DEMO_HOSPITALS[0], name='示例新医院', pinyin_name='z', source_date=AS_OF - timedelta(days=10))
    older = replace(
        DEMO_HOSPITALS[0],
        name='示例旧医院',
        pinyin_name='a',
        capability_score=92.2222222222,
        source_date=AS_OF - timedelta(days=20),
    )
    same_freshness_earlier_name = replace(DEMO_HOSPITALS[0], name='示例甲医院', pinyin_name='a', source_date=AS_OF - timedelta(days=10))
    monkeypatch.setattr(matcher, 'DEMO_HOSPITALS', (fresher, older, same_freshness_earlier_name))

    response = match('冠心病', '上海', 'overall', as_of=AS_OF)

    assert [result.name for result in response.results] == ['示例甲医院', '示例新医院', '示例旧医院']
