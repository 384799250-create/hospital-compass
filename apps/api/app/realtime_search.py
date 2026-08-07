from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
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
