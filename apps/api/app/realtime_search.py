from collections.abc import Mapping
from typing import Literal

from app.schemas import Location

LocationParts = tuple[str, str, str]
Scope = Literal['district', 'city', 'province', 'national']


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
