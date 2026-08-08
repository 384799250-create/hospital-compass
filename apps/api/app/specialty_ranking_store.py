from collections.abc import Iterable, Mapping
from pathlib import Path
import sqlite3

from app.hospital_store import connect
from app.specialty_rankings import SpecialtyRankingEvidence


def initialize_ranking_store(path: Path) -> Path:
    with connect(path) as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS specialty_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hospital TEXT NOT NULL,
                city TEXT NOT NULL,
                specialty TEXT NOT NULL,
                rank INTEGER,
                tier TEXT NOT NULL DEFAULT '',
                year INTEGER NOT NULL,
                source TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT '待核验',
                UNIQUE(hospital, city, specialty, year, source)
            );
            CREATE INDEX IF NOT EXISTS idx_specialty_rankings_lookup
                ON specialty_rankings(hospital, city, specialty, year);
        ''')
    return path


def import_ranking_records(rows: Iterable[Mapping[str, object]], path: Path) -> int:
    initialize_ranking_store(path)
    count = 0
    with connect(path) as db:
        for row in rows:
            evidence = SpecialtyRankingEvidence(
                hospital=str(row.get('hospital') or row.get('name') or '').strip(),
                city=str(row.get('city') or '').strip(),
                specialty=str(row.get('specialty') or row.get('department') or '').strip(),
                rank=_optional_int(row.get('rank')),
                year=int(row.get('year') or 0),
                source=str(row.get('source') or row.get('source_url') or '').strip(),
                verification_status=str(row.get('verification_status') or '待核验'),
            )
            db.execute('''INSERT OR IGNORE INTO specialty_rankings
                (hospital, city, specialty, rank, tier, year, source, verification_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (evidence.hospital, evidence.city, evidence.specialty, evidence.rank,
                 str(row.get('tier') or ''), evidence.year, evidence.source,
                 evidence.verification_status))
            count += db.execute('SELECT changes()').fetchone()[0]
    return count


def ranking_records(*, hospital: str = '', city: str = '', specialty: str = '', path: Path) -> list[dict[str, object]]:
    initialize_ranking_store(path)
    clauses, params = [], []
    for field, value in [('hospital', hospital), ('city', city), ('specialty', specialty)]:
        if value:
            clauses.append(f'{field} = ?')
            params.append(' '.join(value.split()))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    with connect(path) as db:
        rows = db.execute(f'SELECT * FROM specialty_rankings{where} ORDER BY year DESC, rank ASC', params).fetchall()
        return [dict(row) for row in rows]


def _optional_int(value: object) -> int | None:
    if value in (None, ''):
        return None
    return int(value)
