from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.data import DEMO_HOSPITALS, DemoHospital

SCORE_VERSION = 'demo-v1'
SOURCE_MAX_AGE_DAYS = 180
EMERGENCY_TERMS = ('突发胸痛', '呼吸困难', '意识障碍', '大出血')
SPECIALTY_KEYWORDS = {
    '冠心病': '心血管内科',
    '胸痛': '心血管内科',
    '眼睛疼': '眼科',
    '视物模糊': '眼科',
    '红眼': '眼科',
    '鼻塞': '耳鼻咽喉头颈外科',
    '耳痛': '耳鼻咽喉头颈外科',
    '听力下降': '耳鼻咽喉头颈外科',
    '咽痛': '耳鼻咽喉头颈外科',
}
WEIGHTS = {
    'overall': (45, 25, 20, 10),
    'specialty': (60, 20, 10, 10),
    'convenience': (35, 20, 35, 10),
}


class MatchResult(BaseModel):
    id: str
    name: str
    city: str
    demo_label: str
    score: float
    specialties: list[str]
    score_reasons: list[str]
    source_date: date


class MatchResponse(BaseModel):
    emergency: bool
    directions: list[str]
    score_version: str
    results: list[MatchResult]


def match(
    query: str,
    city: str | None,
    priority: Literal['overall', 'specialty', 'convenience'],
    *,
    hospitals: tuple[DemoHospital, ...] | None = None,
    as_of: date | None = None,
) -> MatchResponse:
    """Return deterministic demo-data matches without retaining the query."""
    if any(term in query for term in EMERGENCY_TERMS):
        return MatchResponse(emergency=True, directions=[], score_version=SCORE_VERSION, results=[])

    directions = _directions_for(query)
    if not directions:
        return MatchResponse(emergency=False, directions=[], score_version=SCORE_VERSION, results=[])

    effective_date = as_of or date.today()
    specialty_weight, capability_weight, geography_weight, freshness_weight = _weights_for(priority, city)
    hospital_collection = DEMO_HOSPITALS if hospitals is None else hospitals
    eligible = (
        hospital
        for hospital in hospital_collection
        if is_public_record(hospital, as_of=effective_date)
        and any(direction in hospital.specialties for direction in directions)
    )
    scored = [
        (
            _score(
                hospital,
                directions,
                city,
                specialty_weight,
                capability_weight,
                geography_weight,
                freshness_weight,
                as_of=effective_date,
            ),
            hospital,
        )
        for hospital in eligible
    ]
    scored.sort(key=lambda item: (-item[0], -item[1].source_date.toordinal(), item[1].pinyin_name))
    return MatchResponse(
        emergency=False,
        directions=directions,
        score_version=SCORE_VERSION,
        results=[
            MatchResult(
                id=hospital.id,
                name=hospital.name,
                city=hospital.city,
                demo_label=hospital.demo_label,
                score=score,
                specialties=list(hospital.specialties),
                score_reasons=_score_reasons(hospital, directions, city),
                source_date=hospital.source_date,
            )
            for score, hospital in scored
        ],
    )


def _directions_for(query: str) -> list[str]:
    return list(dict.fromkeys(direction for keyword, direction in SPECIALTY_KEYWORDS.items() if keyword in query))


def _score_reasons(hospital: DemoHospital, directions: list[str], city: str | None) -> list[str]:
    reasons = []
    if any(direction in hospital.specialties for direction in directions) and hospital.specialty_score is not None:
        reasons.append('专科方向匹配')
    if hospital.capability_score is not None:
        reasons.append('服务能力信息')
    if city == hospital.city and hospital.geography_score is not None:
        reasons.append('同城信息')
    reasons.append('来源信息在有效期内')
    return reasons


def _weights_for(priority: str, city: str | None) -> tuple[int, int, int, int]:
    specialty, capability, geography, freshness = WEIGHTS[priority]
    if city is None:
        return specialty + 12, capability + 8, 0, freshness
    return specialty, capability, geography, freshness


def is_public_record(hospital: DemoHospital, *, as_of: date | None = None) -> bool:
    if (
        not hospital.published
        or not hospital.verified
        or type(hospital.source_date) is not date
        or not all((hospital.id, hospital.name, hospital.city, hospital.specialties, hospital.demo_label))
    ):
        return False
    source_age_days = ((as_of or date.today()) - hospital.source_date).days
    return 0 <= source_age_days <= SOURCE_MAX_AGE_DAYS


def _score(
    hospital: DemoHospital,
    directions: list[str],
    city: str | None,
    specialty_weight: int,
    capability_weight: int,
    geography_weight: int,
    freshness_weight: int,
    *,
    as_of: date,
) -> float:
    specialty = (hospital.specialty_score or 0) if any(direction in hospital.specialties for direction in directions) else 0
    capability = hospital.capability_score or 0
    geography = (hospital.geography_score or 0) if city == hospital.city else 0
    freshness = max(0, 100 - (as_of - hospital.source_date).days * 100 / SOURCE_MAX_AGE_DAYS)
    return round(
        specialty * specialty_weight / 100
        + capability * capability_weight / 100
        + geography * geography_weight / 100
        + freshness * freshness_weight / 100,
        4,
    )
