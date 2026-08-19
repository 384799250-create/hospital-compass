"""Import the public 丁香园医院汇 directory into the F: drive database."""

from datetime import UTC, datetime
import json
from pathlib import Path
import re
import time
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.dxy_importer import parse_hospital_list
from app.hospital_store import database_path, upsert_hospital

DATA_DIR = Path(r'F:\hospital-compass-data')
BASE_URL = 'https://y.dxy.cn/hospital/'


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    progress_path = DATA_DIR / 'dxy-import-progress.jsonl'
    first_page = _fetch(1)
    total_pages = int(re.search(r'id="totalcount" value="(\d+)"', first_page).group(1))
    completed = _completed(progress_path)
    imported = 0
    for page in range(1, total_pages + 1):
        if page in completed:
            continue
        try:
            html = first_page if page == 1 else _fetch(page)
            rows = [row for row in parse_hospital_list(html) if row]
            for row in rows:
                upsert_hospital(row, [{'source_url': row['source_url'], 'source_type': '丁香园医院汇公开名录', 'title': '医院公开名录'}])
            imported += len(rows)
            _log(progress_path, {'page': page, 'status': 'completed', 'rows': len(rows)})
        except Exception as error:
            _log(progress_path, {'page': page, 'status': 'failed', 'error': type(error).__name__})
        time.sleep(0.3)
    _log(progress_path, {'status': 'run_completed', 'pages': total_pages, 'imported': imported})


def _fetch(page: int) -> str:
    url = BASE_URL if page == 1 else f'{BASE_URL}?page={page}'
    request = Request(url, headers={'User-Agent': 'hospital-compass-importer/1.0'})
    with urlopen(request, timeout=30) as response:
        return response.read().decode('utf-8', errors='replace')


def _completed(path: Path) -> set[int]:
    if not path.exists():
        return set()
    pages = set()
    for line in path.read_text(encoding='utf-8').splitlines():
        try:
            record = json.loads(line)
            if record.get('status') == 'completed':
                pages.add(int(record['page']))
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return pages


def _log(path: Path, record: dict[str, object]) -> None:
    with path.open('a', encoding='utf-8') as file:
        file.write(json.dumps({'at': datetime.now(UTC).isoformat(), **record}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
