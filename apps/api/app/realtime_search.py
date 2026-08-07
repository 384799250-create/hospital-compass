from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
import re
from typing import Literal
from urllib.parse import urlparse

from app.schemas import Location

from app.bocha_search import SearchDocument

LocationParts = tuple[str, str, str]
Scope = Literal['district', 'city', 'province', 'national']

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
    registration_url: str | None = None
    province: str | None = None
    district: str | None = None
    specialties: tuple[str, ...] = ()
    public_capability: float = 0.0
    completeness: float = 0.0

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
            registration_url=registration_url,
        )

    @property
    def normalized_key(self) -> tuple[str, str]:
        return _normalize(self.name), _normalize(self.city)


def is_registration_url(url: str, official_domains: frozenset[str] = frozenset()) -> bool:
    """Allow only explicitly trusted hospital or authorized-platform domains."""
    parsed = urlparse(url)
    hostname = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or not hostname:
        return False
    return hostname in _AUTHORIZED_REGISTRATION_HOSTS or hostname in official_domains


def merge_hospital_candidates(candidates: list[HospitalCandidate]) -> list[HospitalCandidate]:
    """Merge hospital/city duplicates, keeping only each newest source record."""
    merged: dict[tuple[str, str], HospitalCandidate] = {}
    for candidate in candidates:
        existing = merged.get(candidate.normalized_key)
        if existing is None or _newest_source(candidate) >= _newest_source(existing):
            merged[candidate.normalized_key] = candidate
    return list(merged.values())


def _newest_source(candidate: HospitalCandidate) -> datetime:
    if not candidate.sources:
        return datetime.min.replace(tzinfo=UTC)
    return max(source.fetched_at for source in candidate.sources)


def _normalize(value: str) -> str:
    return ''.join(value.casefold().split())


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


def rank_candidates(
    candidates: Sequence[HospitalCandidate],
    *,
    directions: Sequence[str],
    location: Location | Mapping[str, str] | LocationParts,
    scope: Scope,
    as_of: datetime | None = None,
) -> list[dict[str, object]]:
    """Filter and rank provider candidates without inventing missing records."""
    requested = parse_location(location)
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
        specialty = 100.0 if directions and any(
            direction.casefold() in ' '.join(candidate.specialties).casefold()
            or direction.casefold() in (candidate.name + ' ' + source.title + ' ' + source.snippet).casefold()
            for direction in directions
        ) else 0.0
        capability = candidate.public_capability or _capability_score(source)
        geography = 100.0 if scope == 'national' or (
            candidate_location[0] == requested[0]
            and (scope == 'province' or candidate_location[1] == requested[1])
            and (scope in {'province', 'city'} or candidate_location[2] == requested[2])
        ) else 0.0
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
        eligible.append((score, fetched_at, completeness, candidate.name, candidate, reasons))
    eligible.sort(key=lambda item: (-item[0], -item[1].timestamp(), -item[2], item[3].casefold()))
    results = []
    for score, _, _, _, candidate, reasons in eligible[:10]:
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
        })
    return results


def candidate_from_document(
    document: object,
    *,
    location: Location | Mapping[str, str] | LocationParts,
    official_domains: frozenset[str] = frozenset(),
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
    if not explicit_location and not all(token in searchable_text for token in requested):
        return None
    city = str(metadata.get('city') or requested[1]).strip()
    province = str(metadata.get('province') or requested[0]).strip()
    district = str(metadata.get('district') or requested[2]).strip()
    specialties = metadata.get('specialties') or ()
    if isinstance(specialties, str):
        specialties = (specialties,)
    return HospitalCandidate(
        name=title.split(' - ')[0].split('|')[0].strip(),
        city=city,
        province=province,
        district=district,
        specialties=tuple(str(item) for item in specialties),
        public_capability=_numeric(metadata.get('public_capability', metadata.get('capability_score', 0))),
        completeness=_numeric(metadata.get('completeness', 0)),
        sources=[source],
        registration_url=url if is_registration_url(url, official_domains) else None,
    )


def _capability_score(source: SearchDocument) -> float:
    text = f'{source.title} {source.snippet}'.casefold()
    return 100.0 if any(token in text for token in ('public', '公立', '三级', '三甲', '医保', '卫健')) else 50.0


def _numeric(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(value or 0)))
    except (TypeError, ValueError):
        return 0.0


def _completeness_score(candidate: HospitalCandidate, source: SearchDocument) -> float:
    fields = (candidate.name, candidate.city, source.title, source.url, source.snippet)
    return sum(bool(str(value).strip()) for value in fields) * 20.0
