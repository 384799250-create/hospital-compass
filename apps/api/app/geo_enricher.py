"""Fill missing city labels from local administrative boundary GeoJSON."""

import json
from pathlib import Path

from app.hospital_store import connect


def fill_cities_from_geojson(boundary_path: Path, *, province: str, database_path: Path | None = None) -> int:
    data = json.loads(boundary_path.read_text(encoding='utf-8'))
    boundaries = [(feature.get('properties', {}).get('name', ''), feature.get('geometry')) for feature in data.get('features', [])]
    updated = 0
    with connect(database_path) as connection:
        rows = connection.execute(
            'SELECT id, longitude, latitude FROM hospitals WHERE province = ? AND city = ? AND longitude IS NOT NULL AND latitude IS NOT NULL',
            (province, ''),
        ).fetchall()
        for row in rows:
            city = next((name for name, geometry in boundaries if name and _contains(geometry, row['longitude'], row['latitude'])), '')
            if city:
                connection.execute('UPDATE hospitals SET city = ?, updated_at = updated_at WHERE id = ?', (city, row['id']))
                updated += 1
    return updated


def _contains(geometry: dict | None, longitude: float, latitude: float) -> bool:
    if not geometry:
        return False
    kind = geometry.get('type')
    coordinates = geometry.get('coordinates', [])
    if kind == 'Polygon':
        return _polygon_contains(coordinates, longitude, latitude)
    if kind == 'MultiPolygon':
        return any(_polygon_contains(polygon, longitude, latitude) for polygon in coordinates)
    return False


def _polygon_contains(rings: list, longitude: float, latitude: float) -> bool:
    if not rings or not _ring_contains(rings[0], longitude, latitude):
        return False
    return not any(_ring_contains(hole, longitude, latitude) for hole in rings[1:])


def _ring_contains(ring: list, longitude: float, latitude: float) -> bool:
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = current[0], current[1]
        x2, y2 = previous[0], previous[1]
        intersects = (y1 > latitude) != (y2 > latitude) and longitude < (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
        if intersects:
            inside = not inside
        previous = current
    return inside
