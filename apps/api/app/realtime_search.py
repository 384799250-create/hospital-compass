from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import re
from typing import Literal
from urllib.parse import urlparse

from app.schemas import Location
from app.disease_profiles import DiseaseProfile, PROFILES

from app.bocha_search import SearchDocument

LocationParts = tuple[str, str, str]
Scope = Literal['district', 'city', 'province', 'national']

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
    sources: list[SearchDocument] = field(default_factory=list)
    address: str = ''
    core_advantages: str = ''
    registration_url: str | None = None
    province: str | None = None
    district: str | None = None
    specialties: tuple[str, ...] = ()
    public_capability: float = 0.0
    completeness: float = 0.0
    ranking_evidence: tuple[dict[str, object], ...] = ()

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
        return _normalize(normalize_hospital_name(self.name)), _normalize(self.city)


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
            name=existing.name,
            city=existing.city or candidate.city,
            address=existing.address or candidate.address,
            core_advantages=existing.core_advantages or candidate.core_advantages,
            province=existing.province or candidate.province,
            district=existing.district or candidate.district,
            specialties=tuple(dict.fromkeys(existing.specialties + candidate.specialties)),
            public_capability=max(existing.public_capability, candidate.public_capability),
            completeness=max(existing.completeness, candidate.completeness),
            sources=sources,
            registration_url=existing.registration_url or candidate.registration_url,
            ranking_evidence=existing.ranking_evidence or candidate.ranking_evidence,
        )
    return list(merged.values())


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

_SPECIALTY_ALIASES = {
    '\u5fc3\u8840\u7ba1\u5185\u79d1': ('\u5fc3\u8840\u7ba1\u5185\u79d1', '\u5fc3\u5185\u79d1', '\u5fc3\u810f\u5185\u79d1', '\u5fc3\u8840\u7ba1\u79d1', 'cardiology'),
    '\u547c\u5438\u5185\u79d1': ('\u547c\u5438\u5185\u79d1', '\u547c\u5438\u79d1', 'respiratory medicine', 'pulmonology'),
    '\u795e\u7ecf\u5185\u79d1': ('\u795e\u7ecf\u5185\u79d1', '\u795e\u7ecf\u79d1', 'neurology'),
    '\u6d88\u5316\u5185\u79d1': ('\u6d88\u5316\u5185\u79d1', '\u6d88\u5316\u79d1', 'gastroenterology'),
    '\u9aa8\u79d1': ('\u9aa8\u79d1', '\u9aa8\u5916\u79d1', 'orthopedics'),
    '\u773c\u79d1': ('\u773c\u79d1', 'ophthalmology'),
}


def _expanded_specialty_terms(value: str) -> tuple[str, ...]:
    normalized = value.strip().casefold()
    for canonical, aliases in _SPECIALTY_ALIASES.items():
        if normalized == canonical.casefold() or normalized in {alias.casefold() for alias in aliases}:
            return aliases
    return (value,)


def rank_candidates(
    candidates: Sequence[HospitalCandidate],
    *,
    directions: Sequence[str],
    location: Location | Mapping[str, str] | LocationParts,
    scope: Scope,
    profile_key: str = 'general',
    as_of: datetime | None = None,
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
        specialty = _specialty_strength_score(candidate, source, directions, profile)
        ranking_score = max((float(item.get('score') or 0) for item in candidate.ranking_evidence), default=0.0)
        if ranking_score:
            # The authoritative ranking supplies 50% of specialty strength;
            # live and official evidence remain the other 50%.
            specialty = round(ranking_score * 0.5 + specialty * 0.5, 4)
        capability = max(candidate.public_capability, _capability_score(source, candidate.name, profile))
        if scope == 'national':
            geography = 60.0
        elif scope == 'province':
            geography = 75.0 if candidate_location[0] == requested[0] else 0.0
        elif scope == 'city':
            geography = 100.0 if candidate_location[:2] == requested[:2] else 0.0
        else:
            geography = 100.0 if candidate_location == requested else 0.0
        completeness = candidate.completeness or _completeness_score(candidate, source)
        freshness_completeness = (freshness + completeness) / 2
        official_service = 100.0 if candidate.registration_url else 0.0
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
        eligible.append((score, fetched_at, completeness, candidate.name, candidate, reasons, dimensions))
    eligible.sort(key=lambda item: (-item[0], -item[1].timestamp(), -item[2], item[3].casefold()))
    results = []
    for score, _, _, _, candidate, reasons, dimensions in eligible[:10]:
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
        results.append({
            'id': result_id,
            'name': candidate.name,
            'city': candidate.city,
            'score': score,
            'score_reasons': reasons,
            'sources': source_payload,
            'source_urls': [source['url'] for source in source_payload],
            'fetched_at': max(source['fetched_at'] for source in source_payload),
            'registration_url': candidate.registration_url,
            'address': candidate.address,
            'core_advantages': candidate.core_advantages or source.snippet,
            'core_advantages': source.snippet or '暂无公开资料',
            'match_reason': '；'.join(reasons) or '根据症状、科室和地理范围综合匹配。',
            'evidence_status': '有公开资料' if source.snippet else '暂无公开资料',
            'score_breakdown': dimensions,
            'core_advantages': candidate.core_advantages or source.snippet,
            'specialty_evidence': list(candidate.ranking_evidence),
        })
    return results


def candidate_from_document(
    document: object,
    *,
    location: Location | Mapping[str, str] | LocationParts,
    official_domains: frozenset[str] = frozenset(),
    require_location_evidence: bool = False,
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
    city = str(metadata.get('city') or requested[1]).strip()
    province = str(metadata.get('province') or requested[0]).strip()
    district = str(metadata.get('district') or requested[2]).strip()
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


def _capability_score(source: SearchDocument, hospital_name: str = '', profile: DiseaseProfile | None = None) -> float:
    """Estimate institutional strength from explicit public evidence.

    Name priors are deliberately applied before generic markers so a major
    public hospital is not tied with an otherwise unqualified local listing.
    """
    text = f'{hospital_name} {source.title} {source.snippet}'.casefold()
    if profile and any(term.casefold() in text for term in profile.ranking_terms):
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
    profile_terms = [term.casefold() for term in (profile.ranking_terms if profile else ())]
    if profile_terms and any(term in text or term in specialty_text for term in profile_terms):
        return 96.0
    if not requested or not any(direction in text or direction in specialty_text for direction in requested):
        return 0.0
    if any(token in text for token in (
        '国家临床重点专科', '国家区域医疗中心', '国家医学中心',
        '国家重点专科',
    )) or ('国家' in text and '区域医疗中心' in text):
        return 100.0
    if any(token in text for token in ('省级区域医疗中心', '省重点专科', '省级重点专科', '重点学科')):
        return 90.0
    if any(token in text for token in ('专病中心', '诊疗中心', '医学中心', '特色专科')):
        return 82.0
    if any(direction in specialty_text for direction in requested):
        return 76.0
    if any(token in source.title.casefold() for token in ('科', 'center', 'centre', 'department')):
        return 68.0
    return 58.0


def _numeric(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


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
