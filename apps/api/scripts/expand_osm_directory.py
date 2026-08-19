"""Batch-import OSM hospitals province by province with resumable logs."""

from datetime import UTC, datetime
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.geo_enricher import fill_cities_from_geojson
from app.osm_importer import import_osm_hospitals

DATA_DIR = Path(r'F:\hospital-compass-data')
PROVINCE_FILE = ROOT / 'apps' / 'web' / 'data' / 'province.json'
OVERPASS_ENDPOINTS = (
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
)


def main() -> None:
    arguments = _arguments()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    provinces = json.loads(PROVINCE_FILE.read_text(encoding='utf-8'))
    if arguments.province_code:
        provinces = [province for province in provinces if province['code'] == arguments.province_code]
    if arguments.limit:
        provinces = provinces[:arguments.limit]
    log_path = DATA_DIR / 'osm-batch-progress.jsonl'
    completed = _completed(log_path)
    for province in provinces:
        name, code = province['name'], province['code']
        if name in completed:
            continue
        _log(log_path, {'province': name, 'status': 'started'})
        try:
            boundary_path = DATA_DIR / f'bound-{code}-full.json'
            _download(f'https://geo.datav.aliyun.com/areas_v3/bound/{code}_full.json', boundary_path)
            bbox = _bbox(json.loads(boundary_path.read_text(encoding='utf-8')))
            raw_path = DATA_DIR / f'osm-{code}.json'
            _query_overpass_tiles(bbox, raw_path)
            imported = import_osm_hospitals(raw_path, province=name)
            updated = fill_cities_from_geojson(boundary_path, province=name)
            _log(log_path, {'province': name, 'status': 'completed', 'imported': imported, 'cities_filled': updated})
        except Exception as error:
            _log(log_path, {'province': name, 'status': 'failed', 'error': type(error).__name__})
        time.sleep(2)


def _completed(log_path: Path) -> set[str]:
    if not log_path.exists():
        return set()
    completed = set()
    for line in log_path.read_text(encoding='utf-8').splitlines():
        try:
            record = json.loads(line)
            if record.get('status') == 'completed':
                completed.add(record['province'])
        except json.JSONDecodeError:
            continue
    return completed


def _download(url: str, target: Path) -> None:
    request = Request(url, headers={'User-Agent': 'hospital-compass-importer/1.0'})
    with urlopen(request, timeout=30) as response:
        target.write_bytes(response.read())


def _query_overpass(bbox: tuple[float, float, float, float], target: Path) -> None:
    south, west, north, east = bbox
    query = f'[out:json][timeout:90];nwr["amenity"="hospital"]({south},{west},{north},{east});out center tags;'
    body = urlencode({'data': query}).encode()
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            request = Request(endpoint, data=body, headers={'User-Agent': 'hospital-compass-importer/1.0'}, method='POST')
            with urlopen(request, timeout=120) as response:
                payload = response.read()
            if b'"elements"' not in payload:
                raise ValueError('invalid Overpass response')
            target.write_bytes(payload)
            return
        except Exception as error:
            last_error = error
    raise RuntimeError(f'overpass unavailable: {type(last_error).__name__}')


def _query_overpass_tiles(bbox: tuple[float, float, float, float], target: Path) -> None:
    elements: dict[tuple[str, int], dict] = {}
    failures = 0
    tiles = _split_bbox(bbox, max_span=0.5)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_query_tile, tile, target): tile for tile in tiles}
        for future in as_completed(futures):
            try:
                for element in future.result():
                    key = (element.get('type', ''), element.get('id', 0))
                    elements[key] = element
            except Exception:
                failures += 1
    if not elements:
        raise RuntimeError(f'overpass unavailable: {failures} tile failures')
    target.write_text(json.dumps({'elements': list(elements.values())}, ensure_ascii=False), encoding='utf-8')


def _query_tile(tile: tuple[float, float, float, float], target: Path) -> list[dict]:
    tile_target = target.with_suffix(f'.{tile[0]:.4f}.{tile[1]:.4f}.json')
    try:
        _query_overpass(tile, tile_target)
        return json.loads(tile_target.read_text(encoding='utf-8')).get('elements', [])
    finally:
        tile_target.unlink(missing_ok=True)


def _split_bbox(bbox: tuple[float, float, float, float], max_span: float) -> list[tuple[float, float, float, float]]:
    south, west, north, east = bbox
    tiles = []
    latitude = south
    while latitude < north:
        tile_north = min(latitude + max_span, north)
        longitude = west
        while longitude < east:
            tile_east = min(longitude + max_span, east)
            tiles.append((latitude, longitude, tile_north, tile_east))
            longitude = tile_east
        latitude = tile_north
    return tiles


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--province-code')
    parser.add_argument('--limit', type=int)
    return parser.parse_args()


def _bbox(data: dict) -> tuple[float, float, float, float]:
    points: list[tuple[float, float]] = []
    def visit(value: object) -> None:
        if isinstance(value, list) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            points.append((float(value[0]), float(value[1])))
        elif isinstance(value, list):
            for item in value:
                visit(item)
        elif isinstance(value, dict):
            visit(value.get('coordinates'))
            visit(value.get('geometry'))
    visit(data.get('features', []))
    if not points:
        raise ValueError('boundary has no coordinates')
    west = min(point[0] for point in points)
    east = max(point[0] for point in points)
    south = min(point[1] for point in points)
    north = max(point[1] for point in points)
    return south, west, north, east


def _log(path: Path, record: dict[str, object]) -> None:
    record = {'at': datetime.now(UTC).isoformat(), **record}
    with path.open('a', encoding='utf-8') as file:
        file.write(json.dumps(record, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
