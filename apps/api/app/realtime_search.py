from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import math
import re
from typing import Literal
from urllib.parse import urlparse

from app.schemas import Location
from app.disease_profiles import DiseaseProfile, PROFILES

from app.bocha_search import SearchDocument

LocationParts = tuple[str, str, str]
Scope = Literal['district', 'city', 'province', 'national']
LocationLevel = Literal['province', 'city', 'district']

_LOCATION_ALIASES = {
    '广州市': ('广州市', '广州', 'Guangzhou'), '广东省': ('广东省', '广东', 'Guangdong'),
    '深圳市': ('深圳市', '深圳', 'Shenzhen'), '北京市': ('北京市', '北京', 'Beijing'),
    '上海市': ('上海市', '上海', 'Shanghai'), '浙江省': ('浙江省', '浙江', 'Zhejiang'),
    '杭州市': ('杭州市', '杭州', 'Hangzhou'), '成都市': ('成都市', '成都', 'Chengdu'),
    '武汉市': ('武汉市', '武汉', 'Wuhan'), '南京市': ('南京市', '南京', 'Nanjing'),
}
_ENGLISH_HOSPITAL_NAMES = {
    'guang anmen hospital': '广安门医院',
    "guang'anmen hospital": '广安门医院',
    'chinese pla general hospital': '中国人民解放军总医院',
    'sun yat-sen memorial hospital': '中山大学孙逸仙纪念医院',
    'xiangya hospital central south university': '中南大学湘雅医院',
    "shenzhen luohu people's hospital": '深圳市罗湖区人民医院',
    'shenzhen luohu people\'s hospital': '深圳市罗湖区人民医院',
    'union hospital': '华中科技大学同济医学院附属协和医院',
}
_ENGLISH_CITY_NAMES = {
    'Guangzhou': '广州市', 'Shenzhen': '深圳市', 'Beijing': '北京市',
    'Shanghai': '上海市', 'Hangzhou': '杭州市', 'Wuhan': '武汉市',
    'Nanjing': '南京市', 'Chengdu': '成都市',
}
_HOSPITAL_CITY_HINTS = {
    '华中科技大学同济医学院附属协和医院': '武汉市',
    '复旦大学附属中山医院': '上海市',
    '中国人民解放军总医院': '北京市',
    '深圳市罗湖区人民医院': '深圳市',
}

# These are transparent priors used only when the public source does not
# provide a structured capability score. Exact names cover well-known anchor
# hospitals; the pattern scores keep the rule useful for newly discovered
# hospitals without treating every "医院" result as equally strong.
_HOSPITAL_STRENGTH_PATTERNS = (
    (('\u56fd\u5bb6\u533b\u5b66\u4e2d\u5fc3', '\u56fd\u5bb6\u533b\u7597\u4e2d\u5fc3'), 98.0),
    (('\u5927\u5b66\u9644\u5c5e\u7b2c\u4e00\u533b\u9662', '\u533b\u79d1\u5927\u5b66\u9644\u5c5e\u7b2c\u4e00\u533b\u9662'), 94.0),
    (('\u7701\u4eba\u6c11\u533b\u9662', '\u81ea\u6cbb\u533a\u4eba\u6c11\u533b\u9662'), 92.0),
    (('\u56fd\u5bb6\u533a\u57df\u533b\u7597\u4e2d\u5fc3', '\u7701\u7ea7\u533a\u57df\u533b\u7597\u4e2d\u5fc3'), 90.0),
)
'''
_HOSPITAL_STRENGTH_HINTS = {
    '广东省人民医院': 100.0,
    '中山大学附属第一医院': 98.0,
    '南方医科大学南方医院': 96.0,
    '中山大学孙逸仙纪念医院': 94.0,
    '中山大学附属第三医院': 92.0,
    '广州医科大学附属第一医院': 90.0,
    '广州医科大学附属第二医院': 88.0,
    '暨南大学附属第一医院': 86.0,
    '岭南医院': 68.0,
}
'''

_AUTHORIZED_REGISTRATION_HOSTS = frozenset({
    '114yygh.com',
    'www.114yygh.com',
    'guahao.com',
    'www.guahao.com',
})


@dataclass(frozen=True)
class HospitalCandidate:
    name: str
    city: str
    official_full_name: str = ''
    sources: list[SearchDocument] = field(default_factory=list)
    address: str = ''
    core_advantages: str = ''
    public_introduction: str = ''
    registration_url: str | None = None
    official_website_url: str | None = None
    province: str | None = None
    district: str | None = None
    specialties: tuple[str, ...] = ()
    public_capability: float = 0.0
    completeness: float = 0.0
    ranking_evidence: tuple[dict[str, object], ...] = ()
    tier: str = ''
    hospital_type: str = ''
    capability_evidence: tuple[dict[str, object], ...] = ()

    @classmethod
    def from_document(
        cls,
        *,
        name: str,
        city: str,
        document: SearchDocument | Mapping[str, object],
        official_domains: frozenset[str] = frozenset(),
    ) -> 'HospitalCandidate':
        source = (
            document
            if isinstance(document, SearchDocument)
            else SearchDocument.model_validate(document)
        )
        source_url = str(source.url)
        registration_url = (
            source_url if is_registration_url(source_url, official_domains) else None
        )
        return cls(
            name=name.strip(),
            city=city.strip(),
            sources=[source],
            address='',
            core_advantages='',
            registration_url=registration_url,
        )

    @property
    def normalized_key(self) -> tuple[str, str]:
        identity_name = self.official_full_name or self.name
        return _normalize(normalize_hospital_name(identity_name)), _normalize(self.city)


def is_registration_url(url: str, official_domains: frozenset[str] = frozenset()) -> bool:
    """Allow only explicitly trusted hospital or authorized-platform domains."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not hostname:
        return False
    return hostname in _AUTHORIZED_REGISTRATION_HOSTS or hostname in official_domains


def merge_hospital_candidates(candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
    """Merge hospital/city duplicates while retaining independent evidence."""
    merged: dict[tuple[str, str], HospitalCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.normalized_key)
        if existing is None:
            merged[candidate.normalized_key] = candidate
            continue
        source_by_url = {source.url: source for source in existing.sources}
        source_by_url.update({source.url: source for source in candidate.sources})
        sources = sorted(source_by_url.values(), key=lambda source: source.fetched_at, reverse=True)[:5]
        merged[candidate.normalized_key] = HospitalCandidate(
            name=existing.official_full_name or candidate.official_full_name or existing.name,
            city=existing.city or candidate.city,
            official_full_name=existing.official_full_name or candidate.official_full_name,
            address=existing.address or candidate.address,
            core_advantages=existing.core_advantages or candidate.core_advantages,
            province=existing.province or candidate.province,
            district=existing.district or candidate.district,
            specialties=tuple(dict.fromkeys(existing.specialties + candidate.specialties)),
            public_capability=max(existing.public_capability, candidate.public_capability),
            completeness=max(existing.completeness, candidate.completeness),
            sources=sources,
            registration_url=existing.registration_url or candidate.registration_url,
            official_website_url=existing.official_website_url or candidate.official_website_url,
            ranking_evidence=_merge_evidence(existing.ranking_evidence, candidate.ranking_evidence),
            tier=existing.tier or candidate.tier,
            hospital_type=existing.hospital_type or candidate.hospital_type,
            capability_evidence=_merge_evidence(existing.capability_evidence, candidate.capability_evidence),
        )
    return list(merged.values())


def _merge_evidence(*groups: tuple[dict[str, object], ...]) -> tuple[dict[str, object], ...]:
    """Preserve distinct evidence records while removing exact repeats."""
    merged: list[dict[str, object]] = []
    seen: set[tuple[tuple[str, str], ...]] = set()
    for group in groups:
        for item in group:
            key = tuple(sorted((str(field), repr(value)) for field, value in item.items()))
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return tuple(merged)


def _newest_source(candidate: HospitalCandidate) -> datetime:
    if not candidate.sources:
        return datetime.min.replace(tzinfo=UTC)
    return max(source.fetched_at for source in candidate.sources)


def _normalize(value: str) -> str:
    return ''.join(value.casefold().split())


def normalize_hospital_name(value: str) -> str:
    """Normalize harmless campus suffixes without merging distinct hospitals."""
    name = ' '.join(value.split()).strip()
    for suffix in ('（院本部）', '(院本部)', '（总院）', '(总院)', '院本部', '总院'):
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    return name


def _hospital_name_from_title(title: str) -> str:
    """Prefer the hospital entity in a page title over its department/topic prefix."""
    lowered = title.casefold()
    for english_name, chinese_name in sorted(_ENGLISH_HOSPITAL_NAMES.items(), key=lambda item: -len(item[0])):
        if english_name in lowered:
            return chinese_name
    chinese_entities = re.findall(r'[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z0-9·（）()\-]{1,79}?医院', title)
    if chinese_entities:
        return chinese_entities[-1].strip()
    english_entities = re.findall(r"[A-Za-z][A-Za-z0-9'&.\- ]{1,79}\bHospital(?:\s*\([^)]*\))?", title)
    if english_entities:
        return english_entities[-1].strip(' _-')
    return title.split(' - ')[0].split('|')[0].strip()


_GENERIC_HOSPITAL_NAME_MARKERS = (
    '医院大全', '医院排名', '医院排行榜', '最好的医院', '哪家医院',
    '正规医院', '综合医院', '按三级甲等医院', '科室现有医院',
    '卫生部以及医院', '名医汇', '排行榜', '全国排名', '库基于',
    '为广大患者', '医生信息来自', '执业证', '医师资格', '医生门诊',
)


def parse_location(location: Location | Mapping[str, str]) -> LocationParts:
    """Return a location's exact province, city, and district hierarchy."""
    if not isinstance(location, Location):
        location = Location.model_validate(location)
    return location.province, location.city, location.district


def scope_matches(
    candidate: Location | Mapping[str, str] | LocationParts,
    requested: Location | Mapping[str, str] | LocationParts,
    scope: Scope,
) -> bool:
    """Match only the requested hierarchy; never widen a local scope."""
    if scope == 'national':
        return True

    candidate_province, candidate_city, candidate_district = _location_parts(candidate)
    requested_province, requested_city, requested_district = _location_parts(requested)
    if candidate_province != requested_province:
        return False
    if scope == 'province':
        return True
    if candidate_city != requested_city:
        return False
    if scope == 'city':
        return True
    return candidate_district == requested_district


def _location_parts(
    location: Location | Mapping[str, str] | LocationParts,
) -> LocationParts:
    if isinstance(location, tuple):
        return location
    return parse_location(location)


# The ranking contract intentionally keeps these weights stable and explainable.
RANKING_WEIGHTS = {
    'specialty': 35,
    'public_capability': 25,
    'geography': 20,
    'freshness_completeness': 10,
    'official_service': 10,
}

_SPECIALTY_RANKING_SCOPE_WEIGHTS = {
    'national': 1.00,
    'province': 0.90,
    'city': 0.80,
    'district': 0.70,
}

# Approximate provincial/city-center coordinates used only for a stable,
# offline cross-province proximity score. They are intentionally coarse; exact
# address distance is outside the ranking contract.
_PROVINCE_CENTERS = {
    '\u5317\u4eac\u5e02': (39.9, 116.4), '\u5929\u6d25\u5e02': (39.1, 117.2), '\u6cb3\u5317\u7701': (38.0, 114.5),
    '\u5c71\u897f\u7701': (37.9, 112.5), '\u5185\u8499\u53e4\u81ea\u6cbb\u533a': (40.8, 111.7), '\u8fbd\u5b81\u7701': (41.3, 123.4),
    '\u5409\u6797\u7701': (43.9, 125.3), '\u9ed1\u9f99\u6c5f\u7701': (45.7, 126.6), '\u4e0a\u6d77\u5e02': (31.2, 121.5),
    '\u6c5f\u82cf\u7701': (32.1, 118.8), '\u6d59\u6c5f\u7701': (30.3, 120.2), '\u5b89\u5fbd\u7701': (31.9, 117.3),
    '\u798f\u5efa\u7701': (26.1, 119.3), '\u6c5f\u897f\u7701': (28.7, 115.9), '\u5c71\u4e1c\u7701': (36.7, 117.0),
    '\u6cb3\u5357\u7701': (34.8, 113.6), '\u6e56\u5317\u7701': (30.6, 114.3), '\u6e56\u5357\u7701': (28.2, 112.9),
    '\u5e7f\u4e1c\u7701': (23.4, 113.3), '\u5e7f\u897f\u58ee\u65cf\u81ea\u6cbb\u533a': (22.8, 108.3), '\u6d77\u5357\u7701': (20.0, 110.3),
    '\u91cd\u5e86\u5e02': (29.6, 106.5), '\u56db\u5ddd\u7701': (30.7, 104.1), '\u8d35\u5dde\u7701': (26.6, 106.7),
    '\u4e91\u5357\u7701': (25.0, 102.7), '\u897f\u85cf\u81ea\u6cbb\u533a': (29.7, 91.1), '\u9655\u897f\u7701': (34.3, 108.9),
    '\u7518\u8083\u7701': (36.1, 103.8), '\u9752\u6d77\u7701': (36.6, 101.8), '\u5b81\u590f\u56de\u65cf\u81ea\u6cbb\u533a': (38.5, 106.2),
    '\u65b0\u7586\u7ef4\u543e\u5c14\u81ea\u6cbb\u533a': (43.8, 87.6), '\u9999\u6e2f\u7279\u522b\u884c\u653f\u533a': (22.3, 114.2),
    '\u6fb3\u95e8\u7279\u522b\u884c\u653f\u533a': (22.2, 113.5), '\u53f0\u6e7e\u7701': (25.0, 121.5),
}


def _ranking_scope_weight(value: object) -> float:
    text = str(value or '').casefold()
    if any(token in text for token in ('全国', '国家', '复旦')):
        return _SPECIALTY_RANKING_SCOPE_WEIGHTS['national']
    if any(token in text for token in ('省级', '省单', '省内')):
        return _SPECIALTY_RANKING_SCOPE_WEIGHTS['province']
    if any(token in text for token in ('市级', '地级城市', '城市')):
        return _SPECIALTY_RANKING_SCOPE_WEIGHTS['city']
    if any(token in text for token in ('区级', '县级', '县域')):
        return _SPECIALTY_RANKING_SCOPE_WEIGHTS['district']
    return _SPECIALTY_RANKING_SCOPE_WEIGHTS['district']


def _ranking_scope_value(evidence: Mapping[str, object]) -> object:
    """Prefer an explicit scope, then infer it from the ranking name."""
    values = (
        evidence.get('ranking_scope'),
        evidence.get('scope'),
        evidence.get('ranking_name'),
    )
    scope_markers = ('全国', '国家', '复旦', '省级', '省单', '省内', '市级', '地级城市', '城市', '区级', '县级', '县域')
    for value in values:
        if any(marker in str(value or '') for marker in scope_markers):
            return value
    return next((value for value in values if value), '')


def _province_distance_km(first: str, second: str) -> float | None:
    first_center = _PROVINCE_CENTERS.get(first)
    second_center = _PROVINCE_CENTERS.get(second)
    if not first_center or not second_center:
        return None
    lat1, lon1 = map(math.radians, first_center)
    lat2, lon2 = map(math.radians, second_center)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(haversine))


def _geography_score(candidate: LocationParts, requested: LocationParts, location_level: LocationLevel | None = None) -> float:
    """Score proximity from the smallest location level the user filled in."""
    candidate_province, candidate_city, candidate_district = candidate
    requested_province, requested_city, requested_district = requested
    effective_level = location_level or ('district' if requested_district else 'city' if requested_city else 'province')
    if candidate_province == requested_province:
        if effective_level == 'district':
            if candidate_district == requested_district and candidate_city == requested_city:
                return 100.0
            if candidate_city == requested_city:
                return 85.0
            return 70.0
        if effective_level == 'city':
            if candidate_city == requested_city:
                return 100.0
            return 70.0
        return 100.0

    distance = _province_distance_km(candidate_province, requested_province)
    if distance is None:
        return 0.0
    weight = max(0.05, 1.0 - distance / 4000.0)
    return round(60.0 * weight, 1)

_SPECIALTY_ALIASES = {
    '\u5fc3\u8840\u7ba1\u5185\u79d1': ('\u5fc3\u8840\u7ba1\u5185\u79d1', '\u5fc3\u5185\u79d1', '\u5fc3\u810f\u5185\u79d1', '\u5fc3\u8840\u7ba1\u79d1', 'cardiology'),
    '\u547c\u5438\u5185\u79d1': ('\u547c\u5438\u5185\u79d1', '\u547c\u5438\u79d1', 'respiratory medicine', 'pulmonology'),
    '\u795e\u7ecf\u5185\u79d1': ('\u795e\u7ecf\u5185\u79d1', '\u795e\u7ecf\u79d1', 'neurology'),
    '\u6d88\u5316\u5185\u79d1': ('\u6d88\u5316\u5185\u79d1', '\u6d88\u5316\u79d1', 'gastroenterology'),
    '\u9aa8\u79d1': ('\u9aa8\u79d1', '\u9aa8\u5916\u79d1', 'orthopedics'),
    '\u773c\u79d1': ('\u773c\u79d1', 'ophthalmology'),
}

# Normalize common labels used by public specialty rankings and hospital directories.
_SPECIALTY_ALIASES['心血管内科'] = (
    '心血管内科', '心内科', '心脏内科', '心血管科', '心血管病', '心脏病', '心外科', 'cardiology',
)


def _expanded_specialty_terms(value: str) -> tuple[str, ...]:
    parts = tuple(part.strip() for part in re.split(r'[或/、,，]', value) if part.strip())
    terms: list[str] = []
    for part in parts or (value,):
        normalized = part.casefold()
        for canonical, aliases in _SPECIALTY_ALIASES.items():
            if normalized == canonical.casefold() or normalized in {alias.casefold() for alias in aliases}:
                terms.extend(aliases)
                break
        else:
            terms.append(part)
    return tuple(dict.fromkeys(terms))


_BROADER_SPECIALTY_RANKINGS = {
    '肿瘤内科': ('肿瘤学', '肿瘤科', '肿瘤'),
    '心血管内科': ('心血管病学', '心血管病'),
    '骨科': ('骨科学',),
    '呼吸内科': ('呼吸病学', '呼吸科'),
}

_RELATED_SPECIALTY_RANKINGS = {
    '肿瘤内科': ('胸外科', '呼吸科', '放疗科'),
    '心血管内科': ('心脏外科', '心外科'),
    '骨科': ('康复科',),
}


def _ranking_specialty_match(evidence: Mapping[str, object], directions: Sequence[str]) -> tuple[int, float]:
    ranking_specialty = str(evidence.get('specialty') or '').strip().casefold()
    if not ranking_specialty:
        return 0, 0.0
    for direction in directions:
        direct_terms = tuple(term.casefold() for term in _expanded_specialty_terms(direction))
        if any(term and (ranking_specialty == term or term in ranking_specialty) for term in direct_terms):
            return 2, 1.0
        normalized_direction = direction.strip()
        if any(term.casefold() in ranking_specialty for term in _BROADER_SPECIALTY_RANKINGS.get(normalized_direction, ())):
            return 1, 0.85
        if any(term.casefold() in ranking_specialty for term in _RELATED_SPECIALTY_RANKINGS.get(normalized_direction, ())):
            return 0, 0.65
    return 0, 0.0


def rank_candidates(
    candidates: Sequence[HospitalCandidate],
    *,
    directions: Sequence[str],
    location: Location | Mapping[str, str] | LocationParts,
    scope: Scope,
    location_level: LocationLevel | None = None,
    profile_key: str = 'general',
    as_of: datetime | None = None,
    limit: int | None = 10,
    ignore_geography: bool = False,
) -> list[dict[str, object]]:
    """Filter and rank provider candidates without inventing missing records."""
    requested = parse_location(location)
    profile = next((item for item in PROFILES if item.key == profile_key), None)
    now = as_of or datetime.now(UTC)
    eligible = []
    for candidate in candidates:
        candidate_location = (
            candidate.province or requested[0],
            candidate.city or requested[1],
            candidate.district or requested[2],
        )
        if not scope_matches(candidate_location, requested, scope):
            continue
        if not candidate.name.strip() or not candidate.sources:
            continue
        source = max(candidate.sources, key=lambda item: item.fetched_at)
        fetched_at = source.fetched_at
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=UTC)
        age_days = max(0.0, (now - fetched_at).total_seconds() / 86400)
        freshness = max(0.0, 100.0 - age_days * 100.0 / 180.0)
        ranked_specialties = [
            (item, *_ranking_specialty_match(item, directions))
            for item in candidate.ranking_evidence
            if item.get('rank') and str(item.get('specialty') or '').strip()
        ]
        ranked_specialties = [item for item in ranked_specialties if item[2] > 0]
        exact_rankings = [item for item in ranked_specialties if item[1] == 2]
        selected_rankings = exact_rankings or ranked_specialties
        capability = _institutional_strength_score(candidate, source, profile)
        specialty = _specialty_base_score(capability)
        specialty += max(
            _specialty_evidence_bonus(candidate, source, directions),
            _specialty_ranking_bonus(selected_rankings),
        )
        specialty = round(min(100.0, specialty), 4)
        has_direct_specialty_evidence = bool(selected_rankings) or any(
            _evidence_matches_direction(item, directions)
            for item in candidate.capability_evidence
        ) or _source_has_direct_specialty_evidence(source, directions, profile)
        geography = 100.0 if ignore_geography else _geography_score(candidate_location, requested, location_level)
        completeness = candidate.completeness or _completeness_score(candidate, source)
        freshness_completeness = (freshness + completeness) / 2
        official_service = _official_service_score(
            candidate.official_website_url,
            candidate.registration_url,
        )
        dimensions = {
            'specialty': specialty,
            'public_capability': capability,
            'geography': geography,
            'freshness_completeness': freshness_completeness,
            'official_service': official_service,
        }
        score = round(sum(dimensions[key] * RANKING_WEIGHTS[key] / 100 for key in RANKING_WEIGHTS), 4)
        reasons = [
            f'{key}={round(value, 2)} (weight {RANKING_WEIGHTS[key]})'
            for key, value in dimensions.items()
            if value > 0
        ]
        eligible.append((score, fetched_at, completeness, candidate.name, candidate, source, reasons, dimensions))
    eligible.sort(key=lambda item: (-item[0], -item[1].timestamp(), -item[2], item[3].casefold()))
    results = []
    for score, _, _, _, candidate, source, reasons, dimensions in eligible[:limit]:
        source_payload = [
            {
                'title': source.title,
                'url': source.url,
                'snippet': source.snippet,
                'fetched_at': source.fetched_at.isoformat(),
            }
            for source in candidate.sources
        ]
        result_id = hashlib.sha256(f'{candidate.name}|{candidate.city}'.encode()).hexdigest()[:16]
        core_advantages = candidate.core_advantages or _fallback_core_advantages(candidate, directions, source)
        match_reason = _fallback_match_reason(candidate, directions, requested, scope)
        results.append({
            'id': result_id,
            'name': candidate.name,
            'city': candidate.city,
            'tier': candidate.tier,
            'hospital_type': candidate.hospital_type,
            'specialties': list(candidate.specialties),
            'score': score,
            'score_reasons': reasons,
            'sources': source_payload,
            'source_urls': [source['url'] for source in source_payload],
            'fetched_at': max(source['fetched_at'] for source in source_payload),
            'registration_url': candidate.registration_url,
            'official_website_url': candidate.official_website_url,
            'wechat_appointment': f'{candidate.name}公众号',
            'address': candidate.address,
            'core_advantages': core_advantages,
            'evidence_status': '有公开资料' if source.snippet else '暂无公开资料',
            'score_breakdown': dimensions,
            'has_direct_specialty_evidence': has_direct_specialty_evidence,
            'match_reason': match_reason,
            'core_advantages': core_advantages,
            'specialty_evidence': _visible_evidence(candidate, source, directions, profile),
            'database_evidence': {
                'province': candidate.province,
                'city': candidate.city,
                'district': candidate.district,
                'address': candidate.address,
                'tier': candidate.tier,
                'hospital_type': candidate.hospital_type,
                'capabilities': list(candidate.capability_evidence),
                'rankings': list(candidate.ranking_evidence),
                'public_introduction': candidate.public_introduction,
                'official_service_url': candidate.registration_url,
            },
        })
    return results


def _deduplicate_evidence(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    unique: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for item in items:
        kind = 'ranking' if item.get('rank') or item.get('ranking_source_name') else 'capability'
        key = (
            kind,
            str(item.get('specialty') or item.get('department') or '').strip(),
            item.get('rank') if kind == 'ranking' else str(item.get('strength_level') or '').strip(),
            item.get('year') if kind == 'ranking' else str(item.get('diagnosis_scope') or '').strip(),
            str(item.get('ranking_source_name') or item.get('ranking_name') or item.get('source') or '').strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(dict(item))
    return unique


_DIRECT_SPECIALTY_MARKERS = (
    '国家临床重点专科', '国家重点专科', '国家医学中心', '国家区域医疗中心',
    '国家心血管区域医疗中心', '省级重点专科', '省重点专科', '省级区域医疗中心',
    '重点学科', '专病中心', '诊疗中心', '医学中心', '特色专科',
)


def _source_capability_label(sentence: str) -> str:
    """Reduce a source sentence to the specialty-strength label it proves."""
    for marker in _DIRECT_SPECIALTY_MARKERS:
        marker_index = sentence.find(marker)
        if marker_index < 0:
            continue
        label_end = marker_index + len(marker)
        qualifier = re.match(r'[（(][^）)]{1,30}[）)]', sentence[label_end:])
        if qualifier:
            label_end += len(qualifier.group(0))
        label_start = max(sentence.rfind('，', 0, marker_index), sentence.rfind('；', 0, marker_index)) + 1
        label = re.sub(r'^.*(?:为|是|拥有|设有)', '', sentence[label_start:label_end]).strip()
        if label:
            return label
    return sentence


def _source_capability_evidence(
    source: SearchDocument,
    directions: Sequence[str],
    profile: DiseaseProfile | None,
) -> list[dict[str, object]]:
    """Expose the explicit source sentences that establish specialty points."""
    if not _source_has_direct_specialty_evidence(source, directions, profile):
        return []
    evidence: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for sentence in re.split(r'[。！？；;]', source.snippet):
        sentence = sentence.strip()
        if not sentence or not any(marker in sentence for marker in _DIRECT_SPECIALTY_MARKERS):
            continue
        for direction in directions:
            department = str(direction).strip()
            terms = _expanded_specialty_terms(department)
            if not department or not any(term.casefold() in sentence.casefold() for term in terms):
                continue
            key = (department, sentence)
            if key in seen:
                continue
            seen.add(key)
            evidence.append({
                'department': department,
                'diagnosis_scope': sentence,
                'strength_level': _source_capability_label(sentence),
                'source': source.url,
                'ranking_source_name': source.title,
                'verification_status': '公开资料',
            })
    return evidence


def _visible_evidence(
    candidate: HospitalCandidate,
    source: SearchDocument,
    directions: Sequence[str],
    profile: DiseaseProfile | None,
) -> list[dict[str, object]]:
    evidence = [*candidate.capability_evidence, *candidate.ranking_evidence]
    if not directions:
        general_rankings = _ordered_general_rankings(candidate)
        non_general_rankings = [
            item for item in candidate.ranking_evidence
            if not _is_general_institutional_ranking(item)
        ]
        return _deduplicate_evidence([
            *candidate.capability_evidence,
            *_source_capability_evidence(source, directions, profile),
            *non_general_rankings,
            *general_rankings,
        ])
    directional = [item for item in evidence if _evidence_matches_direction(item, directions)]
    source_capabilities = _source_capability_evidence(source, directions, profile)
    general_rankings = _ordered_general_rankings(candidate)
    return _deduplicate_evidence([*directional, *source_capabilities, *general_rankings])


def _evidence_matches_direction(item: Mapping[str, object], directions: Sequence[str]) -> bool:
    terms = tuple(
        term.casefold()
        for direction in directions
        for term in _expanded_specialty_terms(str(direction))
        if term.strip()
    )
    text = ' '.join(
        str(item.get(key) or '').casefold()
        for key in ('department', 'specialty', 'diagnosis_scope')
    )
    return bool(text and any(term in text or text in term for term in terms))


_SPECIALTY_BASELINE_RATIO = 0.60
_SPECIALTY_RANKING_BONUS_CAP = 40.0


def _specialty_base_score(institutional_strength: float) -> float:
    return round(max(0.0, min(100.0, institutional_strength)) * _SPECIALTY_BASELINE_RATIO, 4)


def _specialty_level_bonus(text: str) -> float:
    value = text.casefold()
    if any(marker in value for marker in ('国家临床重点专科', '国家重点专科', '国家级重点', '国家医学中心', '国家区域医疗中心')):
        return 25.0
    if any(marker in value for marker in ('省级区域医疗中心', '省级重点专科', '省重点专科', '省级重点学科')):
        return 18.0
    if '县级' in value and any(marker in value for marker in ('重点学科', '重点专科')):
        return 8.0
    if any(marker in value for marker in ('市级重点学科', '市重点学科', '市级重点专科', '市重点专科', '院内临床重点专科')):
        return 12.0
    if any(marker in value for marker in ('重点学科', '重点专科', '专病中心', '诊疗中心', '医学中心', '特色专科')):
        return 12.0
    return 0.0


def _text_matches_direction(text: str, directions: Sequence[str]) -> bool:
    value = text.casefold()
    terms = tuple(
        term.casefold()
        for direction in directions
        for term in _expanded_specialty_terms(str(direction))
        if term.strip()
    )
    return bool(terms and any(term in value for term in terms))


def _specialty_evidence_bonus(
    candidate: HospitalCandidate,
    source: SearchDocument,
    directions: Sequence[str],
) -> float:
    evidence_texts = [
        ' '.join(str(item.get(key) or '') for key in ('department', 'specialty', 'diagnosis_scope', 'strength_level'))
        for item in candidate.capability_evidence
        if _evidence_matches_direction(item, directions)
    ]
    evidence_texts.extend(
        sentence.strip()
        for sentence in re.split(r'[。！？；;]', source.snippet)
        if sentence.strip() and _text_matches_direction(sentence, directions)
    )
    bonuses = [_specialty_level_bonus(text) for text in evidence_texts]
    strongest = max(bonuses, default=0.0)
    if strongest > 0:
        return strongest
    if evidence_texts or any(_text_matches_direction(item, directions) for item in candidate.specialties):
        return 2.0
    return 0.0


def _national_specialty_ranking_bonus(rank: object) -> float:
    try:
        position = int(rank)
    except (TypeError, ValueError):
        return 0.0
    if 1 <= position <= 20:
        weight = 1.0 - (position - 1) * 0.30 / 19
    elif 20 < position <= 100:
        weight = 0.70 - (position - 20) * 0.45 / 80
    else:
        return 0.0
    return round(_SPECIALTY_RANKING_BONUS_CAP * weight, 4)


def _specialty_ranking_bonus(ranked_specialties: Sequence[tuple[Mapping[str, object], int, float]]) -> float:
    if not ranked_specialties:
        return 0.0
    exact = [item for item in ranked_specialties if item[1] == 2]
    selected = exact or list(ranked_specialties)
    bonuses = []
    for evidence, _, direction_match in selected:
        scope = evidence.get('ranking_scope') or evidence.get('scope') or evidence.get('ranking_name')
        scope_weight = _ranking_scope_weight(scope)
        if scope_weight == _SPECIALTY_RANKING_SCOPE_WEIGHTS['national']:
            bonuses.append(_national_specialty_ranking_bonus(evidence.get('rank')) * direction_match)
            continue
        bonuses.append(
            float(evidence.get('score') or 0)
            * scope_weight
            * direction_match
            * 0.40
        )
    return round(min(_SPECIALTY_RANKING_BONUS_CAP, max(0.0, max(bonuses, default=0.0))), 4)


def _fallback_core_advantages(candidate: HospitalCandidate, directions: Sequence[str], source: SearchDocument) -> str:
    direction_terms = tuple(
        term.casefold()
        for direction in directions
        for term in _expanded_specialty_terms(direction)
        if term.strip()
    )
    ranked = [
        item for item in candidate.ranking_evidence
        if item.get('rank') and item.get('specialty') and (
            not direction_terms
            or any(
                term in str(item.get('specialty') or '').casefold()
                for term in direction_terms
            )
        )
    ]
    capabilities = [
        item for item in candidate.capability_evidence
        if item.get('department') and (
            not direction_terms
            or any(term in str(item.get('department') or '').casefold() or term in str(item.get('diagnosis_scope') or '').casefold() for term in direction_terms)
        )
    ]
    matching_specialties = [
        specialty for specialty in candidate.specialties
        if not direction_terms or any(
            term in specialty.casefold() or specialty.casefold() in term
            for term in direction_terms
        )
    ]
    sentences: list[str] = []
    if ranked:
        item = ranked[0]
        scope = str(item.get('ranking_scope') or item.get('scope') or item.get('ranking_name') or '公开榜单').strip()
        specialty = str(item.get('specialty') or '').strip()
        title = str(item.get('ranking_source_name') or '').strip()
        publisher = str(item.get('ranking_publisher') or '').strip()
        if title:
            publisher_part = f'{publisher}发布的' if publisher else ''
            sentences.append(f'该院{specialty}在{publisher_part}《{title}》中位列第{item.get("rank")}名。')
        else:
            sentences.append(f"该院{specialty}在{scope}排名中位列第{item.get('rank')}名。")
    elif capabilities:
        item = capabilities[0]
        department = str(item.get('department') or '').strip()
        detail = str(item.get('strength_level') or item.get('diagnosis_scope') or '').strip()
        sentences.append(
            f"公开资料显示，该院{department}{'具备' + detail if detail else '提供相关诊疗服务'}。"
        )
    elif matching_specialties:
        sentences.append(f'公开资料显示，该院开设{matching_specialties[0]}相关诊疗服务。')
    displayed_general_ranking = _displayed_general_ranking(candidate)
    inferred_type = candidate.hospital_type or _infer_hospital_type(candidate.public_introduction)
    if displayed_general_ranking:
        item = displayed_general_ranking
        source_name = str(item.get('ranking_source_name') or '').strip()
        if source_name:
            ranking_sentence = f"公开资料显示，医院在《{source_name}》中位列第{item.get('rank')}名"
        else:
            year = f"{item.get('year')}年" if item.get('year') else ''
            scope = item.get('ranking_scope') or item.get('scope') or '公开榜单'
            name = item.get('ranking_name') or '综合排名'
            ranking_sentence = f"公开资料显示，医院在{year}{scope}{name}中位列第{item.get('rank')}名"
        if not ranked and (candidate.tier or inferred_type):
            institution = ''.join(part for part in (candidate.tier, inferred_type) if part)
            ranking_sentence += f'，该院为{institution}'
        sentences.append(f'{ranking_sentence}。')
    if candidate.tier or inferred_type:
        if not displayed_general_ranking:
            institution = ''.join(part for part in (candidate.tier, inferred_type) if part)
            sentences.append(f'该院为{institution}。')
    elif not sentences:
        snippet = source.snippet.strip().split('。', 1)[0]
        if snippet and len(snippet) <= 80:
            sentences.append(f'公开资料显示，医院提供{snippet}。')
        else:
            sentences.append('当前公开资料有限，医院综合服务信息待进一步核实。')

    profile = _factual_profile_sentence(candidate.public_introduction)
    if profile and profile not in sentences:
        sentences.append(profile)

    if directions and not ranked:
        sentences.append(_missing_specialty_note(directions))
        sentences = sentences[:-1][:2] + [sentences[-1]]
    return ''.join(sentences[:3])[:300]


def _direction_label(directions: Sequence[str]) -> str:
    for direction in directions:
        label = re.split(r'[或/、,，]', str(direction), maxsplit=1)[0].strip()
        if label:
            return label
    return '当前就医'


def _missing_specialty_note(directions: Sequence[str]) -> str:
    direction = _direction_label(directions)
    return f'当前公开信息中未见与{direction}方向直接对应的专科排名，建议结合{direction}门诊安排进一步确认。'


def _factual_profile_sentence(public_introduction: str) -> str:
    promotional_markers = ('愿景', '使命', '一流', '致力于', '秉承', '追求', '坚持')
    for sentence in re.split(r'[。！？]', public_introduction.strip()):
        sentence = sentence.strip()
        if not sentence or len(sentence) > 120 or any(marker in sentence for marker in promotional_markers):
            continue
        if ('妇女和儿童' in sentence or '妇女儿童' in sentence) and ('医疗保健' in sentence or '健康服务' in sentence):
            return '医院提供妇女和儿童相关医疗保健服务。'
        if any(term in sentence for term in ('临床科室', '诊疗范围', '诊疗服务', '健康服务')):
            return f'{sentence}。'
        if any(term in sentence for term in ('认证', '医疗、科研', '医疗、教学', '预防保健')):
            certifications = re.findall(
                r'(?:通过(?:国际)?|获)([A-Z][A-Z0-9-]*)(?:国际)?认证',
                sentence,
            )
            if certifications and '集医疗' in sentence:
                unique_certifications = list(dict.fromkeys(certifications))
                certification_text = '和'.join(
                    f'国际{name}认证' if index == 0 else f'{name}国际认证'
                    for index, name in enumerate(unique_certifications)
                )
                return f'医院已通过{certification_text}，集医疗、科研、教学、预防保健为一体，能够提供综合医疗服务。'
            normalized = re.sub(r'^[^，。！？]{2,40}医院(?:是|为)', '', sentence)
            return f'医院{normalized}。'
    return ''


def _infer_hospital_type(public_introduction: str) -> str:
    for hospital_type in ('中西医结合医院', '妇幼保健院', '专科医院', '综合医院'):
        if hospital_type in public_introduction:
            return hospital_type
    return ''


def _fallback_match_reason(candidate: HospitalCandidate, directions: Sequence[str], requested: LocationParts, scope: Scope) -> str:
    direction = '、'.join(directions) or '当前就医方向'
    place = candidate.city or requested[1]
    scope_label = {'district': '区/县级', 'city': '市级', 'province': '省级', 'national': '全国'}[scope]
    ranked = [item for item in candidate.ranking_evidence if item.get('rank') and item.get('specialty')]
    direction_terms = tuple(term.casefold() for term in directions if term.strip())
    evidence = [
        item for item in candidate.capability_evidence
        if item.get('department') and (
            not direction_terms
            or any(term in str(item.get('department') or '').casefold() or term in str(item.get('diagnosis_scope') or '').casefold() for term in direction_terms)
        )
    ]
    if ranked:
        ranking_text = '、'.join(f"{item.get('specialty')}排名第{item.get('rank')}名" for item in ranked[:2])
        return f'用户描述与{direction}相关；该院有{ranking_text}的公开证据，位于{place}，纳入当前{scope_label}范围。'
    if evidence:
        departments = '、'.join(str(item.get('department')) for item in evidence[:2])
        return f'用户描述与{direction}相关；该院公开资料包含{departments}能力证据，位于{place}，纳入当前{scope_label}范围。'
    return f'用户描述与{direction}相关；该院位于{place}，纳入当前{scope_label}范围，但暂未找到直接对应的专科排名证据。'


def candidate_from_document(
    document: object,
    *,
    location: Location | Mapping[str, str] | LocationParts,
    official_domains: frozenset[str] = frozenset(),
    require_location_evidence: bool = False,
    require_district_evidence: bool = False,
) -> HospitalCandidate | None:
    """Convert a search document to a conservative hospital candidate."""
    requested = parse_location(location)
    title = str(getattr(document, 'title', '') or (document.get('title', '') if isinstance(document, Mapping) else '')).strip()
    url = str(getattr(document, 'url', '') or (document.get('url', '') if isinstance(document, Mapping) else '')).strip()
    snippet = str(getattr(document, 'snippet', '') or (document.get('snippet', '') if isinstance(document, Mapping) else '')).strip()
    fetched_at = getattr(document, 'fetched_at', None) or (document.get('fetched_at') if isinstance(document, Mapping) else None)
    if not title or not url or fetched_at is None:
        return None
    try:
        source = document if isinstance(document, SearchDocument) else SearchDocument.model_validate({
            'title': title, 'url': url, 'snippet': snippet, 'fetched_at': fetched_at,
        })
    except Exception:
        return None
    metadata = document if isinstance(document, Mapping) else document.__dict__
    explicit_location = any(metadata.get(key) for key in ('city', 'province', 'district'))
    searchable_text = f'{title} {snippet} {url}'
    if any(marker in searchable_text.casefold() for marker in (
        '执业证', '医师资格', '医生门诊', '本站已通过实名认证',
        '医生个人主页', '医生介绍',
    )):
        return None
    location_tokens = []
    for part in requested[:2]:
        location_tokens.extend(_LOCATION_ALIASES.get(part, (part,)))
    has_location_evidence = any(token.casefold() in searchable_text.casefold() for token in location_tokens)
    city_tokens = _LOCATION_ALIASES.get(requested[1], (requested[1],))
    has_city_evidence = any(token.casefold() in searchable_text.casefold() for token in city_tokens)
    has_hospital_entity = any(term in searchable_text.casefold() for term in ('hospital', 'medical center', 'medical centre', '医院', '医科大学'))
    requested_city = requested[1]
    for english_city, chinese_city in _ENGLISH_CITY_NAMES.items():
        if english_city.casefold() in searchable_text.casefold() and chinese_city != requested_city and not explicit_location:
            return None
    if not explicit_location and not has_hospital_entity:
        return None
    if require_location_evidence and not explicit_location and not has_city_evidence:
        return None
    district = str(metadata.get('district') or '').strip()
    if require_district_evidence:
        district_tokens = _LOCATION_ALIASES.get(requested[2], (requested[2],))
        has_district_evidence = any(token.casefold() in searchable_text.casefold() for token in district_tokens)
        if not district and not has_district_evidence:
            return None
    city = str(metadata.get('city') or requested[1]).strip()
    province = str(metadata.get('province') or requested[0]).strip()
    district = district or requested[2]
    specialties = metadata.get('specialties') or ()
    if isinstance(specialties, str):
        specialties = (specialties,)
    # Search snippets often contain the actual provider name while the title
    # is a generic ranking or department page heading.
    hospital_name = _hospital_name_from_title(title)
    # If the title is a generic search/ranking heading, use the snippet to
    # recover the provider entity. Do not let a trailing phrase such as
    # "心血管内科医院" replace the actual hospital named in the title.
    if hospital_name == title or '医院' not in hospital_name:
        hospital_name = _hospital_name_from_title(f'{title} {snippet}')
    if '院区' in hospital_name and '(' in hospital_name:
        hospital_name = hospital_name.rsplit('(', 1)[-1].strip(' )）')
    if '院区' in hospital_name and '（' in hospital_name:
        hospital_name = hospital_name.rsplit('（', 1)[-1].strip(' ）)')
    if any(marker in hospital_name for marker in _GENERIC_HOSPITAL_NAME_MARKERS):
        return None
    if '医院' not in hospital_name and 'hospital' not in hospital_name.casefold():
        return None
    if not re.search(r'[\u4e00-\u9fff]', hospital_name):
        return None
    hinted_city = _HOSPITAL_CITY_HINTS.get(hospital_name)
    if hinted_city and hinted_city != requested[1]:
        return None
    return HospitalCandidate(
        name=hospital_name,
        city=city,
        province=province,
        district=district,
        specialties=tuple(str(item) for item in specialties),
        public_capability=_numeric(metadata.get('public_capability', metadata.get('capability_score', 0))),
        completeness=_numeric(metadata.get('completeness', 0)),
        sources=[source],
        registration_url=url if is_registration_url(url, official_domains) else None,
    )


_SPECIALIZED_INSTITUTION_RANKING_TERMS = (
    '\u4e2d\u533b', '\u4e2d\u897f\u533b\u7ed3\u5408', '\u5987\u5e7c', '\u513f\u7ae5', '\u80bf\u7624',
    '\u53e3\u8154', '\u773c\u79d1', '\u7cbe\u795e', '\u5eb7\u590d', '\u4f20\u67d3\u75c5', '\u4e13\u79d1\u533b\u9662',
)


def _is_general_institutional_ranking(evidence: Mapping[str, object]) -> bool:
    if not evidence.get('rank') or str(evidence.get('specialty') or '').strip():
        return False
    text = ' '.join(str(evidence.get(key) or '') for key in ('ranking_name', 'ranking_scope', 'scope', 'source')).casefold()
    return not any(term in text for term in _SPECIALIZED_INSTITUTION_RANKING_TERMS)


def _displayed_general_ranking(candidate: HospitalCandidate) -> Mapping[str, object] | None:
    """Choose the verified best rank from the first displayed ranking list."""
    general_rankings = [
        item for item in candidate.ranking_evidence
        if _is_general_institutional_ranking(item)
    ]
    if not general_rankings:
        return None
    first_list_key = _general_ranking_list_key(general_rankings[0])
    matching_list = [
        item for item in general_rankings
        if _general_ranking_list_key(item) == first_list_key
    ]
    verified = [item for item in matching_list if _ranking_is_verified(item)]
    return min(verified or matching_list, key=_ranking_position)


def _ordered_general_rankings(candidate: HospitalCandidate) -> list[dict[str, object]]:
    """Place the selected general ranking first wherever evidence is shown."""
    displayed = _displayed_general_ranking(candidate)
    general_rankings = [
        item for item in candidate.ranking_evidence
        if _is_general_institutional_ranking(item)
    ]
    if displayed is None:
        return general_rankings
    return [displayed, *(item for item in general_rankings if item is not displayed)]


def _general_ranking_list_key(evidence: Mapping[str, object]) -> tuple[str, str, str, str]:
    return (
        str(evidence.get('ranking_source_id') or evidence.get('ranking_source_name') or evidence.get('ranking_name') or '').strip(),
        str(evidence.get('year') or '').strip(),
        str(evidence.get('ranking_scope') or evidence.get('scope') or '').strip(),
        str(evidence.get('specialty') or '').strip(),
    )


def _ranking_is_verified(evidence: Mapping[str, object]) -> bool:
    return str(evidence.get('verification_status') or '').strip() in {'verified', '已核验', '已通过'}


def _ranking_position(evidence: Mapping[str, object]) -> int:
    try:
        return int(evidence.get('rank') or 2**31 - 1)
    except (TypeError, ValueError):
        return 2**31 - 1


def _overall_ranking_score(evidence: Mapping[str, object]) -> float:
    try:
        rank = int(evidence.get('rank') or 0)
    except (TypeError, ValueError):
        return 0.0
    if rank <= 0:
        return 0.0
    try:
        max_rank = int(evidence.get('ranking_max_rank') or 2000)
    except (TypeError, ValueError):
        max_rank = 2000
    max_rank = max(max_rank, rank, 500)
    if rank <= 500:
        # Steeper early decline: 1st is 100 and 500th is 80.
        base_score = 100.0 - (rank - 1) / 499 * 20.0
    else:
        # The remaining range declines linearly from 80 to 60.
        base_score = 80.0 - (rank - 500) / (max_rank - 500) * 20.0
    scope_weight = _ranking_scope_weight(_ranking_scope_value(evidence))
    return round(max(0.0, min(100.0, base_score * scope_weight)), 1)


def _institutional_strength_score(candidate: HospitalCandidate, source: SearchDocument, profile: DiseaseProfile | None = None) -> float:
    displayed_general_ranking = _displayed_general_ranking(candidate)
    if displayed_general_ranking:
        return _overall_ranking_score(displayed_general_ranking)
    if candidate.public_capability > 0:
        return candidate.public_capability
    return _capability_score(source, candidate.name, profile)


def _capability_score(source: SearchDocument, hospital_name: str = '', profile: DiseaseProfile | None = None) -> float:
    """Estimate institutional strength from explicit public evidence.

    Name priors are deliberately applied before generic markers so a major
    public hospital is not tied with an otherwise unqualified local listing.
    """
    text = f'{hospital_name} {source.title} {source.snippet}'.casefold()
    evidence_text = f'{source.title} {source.snippet}'.casefold()
    if profile and any(term.casefold() in evidence_text for term in profile.ranking_terms):
        return 92.0
    for patterns, score in _HOSPITAL_STRENGTH_PATTERNS:
        if any(token.casefold() in text for token in patterns):
            return score
    if any(token in text for token in ('国家医学中心', '国家区域医疗中心', '国家临床重点专科')):
        return 96.0
    if any(token in text for token in ('省级区域医疗中心', '省重点专科', '省级重点专科')):
        return 86.0
    if any(token in text for token in ('三甲', '三级甲等', '公立', 'public', '卫健委直属')):
        return 78.0
    if any(token in text for token in ('医保', '综合医院', '专科医院')):
        return 62.0
    return 50.0


def _specialty_strength_score(
    candidate: HospitalCandidate,
    source: SearchDocument,
    directions: Sequence[str],
    profile: DiseaseProfile | None = None,
) -> float:
    """Score the strength of specialty evidence instead of keyword presence."""
    text = f'{candidate.name} {source.title} {source.snippet}'.casefold()
    requested = [
        term.casefold()
        for direction in directions if direction.strip()
        for term in _expanded_specialty_terms(direction)
    ]
    specialty_text = ' '.join(candidate.specialties).casefold()
    evidence_text = f'{source.title} {source.snippet}'.casefold()
    capability_text = ' '.join(
        f"{item.get('department', '')} {item.get('diagnosis_scope', '')} {item.get('strength_level', '')}"
        for item in candidate.capability_evidence
    ).casefold()
    profile_terms = [term.casefold() for term in (profile.ranking_terms if profile else ())]
    if profile_terms and any(term in evidence_text or term in specialty_text or term in capability_text for term in profile_terms):
        return 96.0
    if not requested or not any(direction in evidence_text or direction in specialty_text or direction in capability_text for direction in requested):
        return 0.0
    matched_capabilities = [item for item in candidate.capability_evidence if any(
        term in ' '.join(str(item.get(key) or '') for key in ('department', 'diagnosis_scope')).casefold()
        for term in requested
    )]
    if matched_capabilities:
        levels = ' '.join(str(item.get('strength_level') or '') for item in matched_capabilities)
        if any(token in levels for token in ('国家级', '国家重点', '国家临床重点')):
            return 100.0
        if any(token in levels for token in ('省级', '省重点', '重点')):
            return 90.0
        return 82.0
    if any(token in evidence_text for token in (
        '国家临床重点专科', '国家区域医疗中心', '国家医学中心',
        '国家重点专科',
    )) or ('国家' in evidence_text and '区域医疗中心' in evidence_text):
        return 100.0
    if any(token in evidence_text for token in ('省级区域医疗中心', '省重点专科', '省级重点专科', '重点学科')):
        return 90.0
    if any(token in evidence_text for token in ('专病中心', '诊疗中心', '医学中心', '特色专科')):
        return 82.0
    matched_terms = [term for term in requested if term in specialty_text]
    if matched_terms:
        canonical = directions[0].casefold() if directions else ''
        return min(88.0, 80.0 + (4.0 if canonical and canonical in specialty_text else 0.0) + min(4.0, len(matched_terms) - 1))
    if any(token in source.title.casefold() for token in ('科', 'center', 'centre', 'department')):
        return 68.0
    return 58.0


def _source_has_direct_specialty_evidence(
    source: SearchDocument,
    directions: Sequence[str],
    profile: DiseaseProfile | None,
) -> bool:
    """Only explicit specialty-strength statements may score without structured evidence."""
    text = f'{source.title} {source.snippet}'.casefold()
    if profile and any(term.casefold() in text for term in profile.ranking_terms):
        return True
    requested = [
        term.casefold()
        for direction in directions if direction.strip()
        for term in _expanded_specialty_terms(direction)
    ]
    if not requested or not any(term in text for term in requested):
        return False
    return any(marker in text for marker in _DIRECT_SPECIALTY_MARKERS)


def _has_explicit_visible_specialty_evidence(result: Mapping[str, object]) -> bool:
    """Recognize direct evidence retained in a response before legacy score repair."""
    evidence_items = result.get('specialty_evidence') or ()
    if not isinstance(evidence_items, Sequence) or isinstance(evidence_items, (str, bytes)):
        return False
    for item in evidence_items:
        if not isinstance(item, Mapping):
            continue
        if not str(item.get('department') or item.get('specialty') or '').strip():
            continue
        if item.get('rank'):
            return True
        evidence_text = ' '.join(str(item.get(key) or '') for key in (
            'strength_level', 'diagnosis_scope', 'credential_name',
        ))
        if _specialty_level_bonus(evidence_text) > 0:
            return True
    return False


def normalize_result_specialty_score(result: dict[str, object]) -> dict[str, object]:
    """Keep legacy results aligned with the calibrated specialty baseline."""
    if result.get('has_direct_specialty_evidence') is not False:
        return result
    if _has_explicit_visible_specialty_evidence(result):
        result['has_direct_specialty_evidence'] = True
        return result
    breakdown = dict(result.get('score_breakdown') or {})
    breakdown['specialty'] = _specialty_base_score(_numeric(breakdown.get('public_capability')))
    if all(key in breakdown for key in RANKING_WEIGHTS):
        result['score'] = round(sum(
            float(breakdown[key] or 0) * weight / 100
            for key, weight in RANKING_WEIGHTS.items()
        ), 4)
        result['score_reasons'] = [
            f'{key}={round(float(value), 2)} (weight {RANKING_WEIGHTS[key]})'
            for key, value in breakdown.items()
            if key in RANKING_WEIGHTS and float(value or 0) > 0
        ]
    result['score_breakdown'] = breakdown
    return result


def _numeric(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _official_service_score(
    official_website_url: str | None,
    registration_url: str | None,
) -> float:
    """Score the availability of an official website or appointment endpoint."""
    if official_website_url or registration_url:
        return 100.0
    return 60.0


def _completeness_score(candidate: HospitalCandidate, source: SearchDocument) -> float:
    fields = (
        candidate.name,
        candidate.city,
        candidate.address,
        candidate.specialties,
        source.title,
        source.url,
        source.snippet,
        candidate.registration_url,
    )
    present = sum(bool(value) for value in fields)
    return min(100.0, present / len(fields) * 100.0)
