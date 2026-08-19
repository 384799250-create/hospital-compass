from collections.abc import Iterable, Mapping
from pathlib import Path
import sqlite3
from urllib.parse import urlparse, urlunparse

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
    with connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'hospital_rankings' in tables and 'ranking_sources' in tables and 'hospitals' in tables:
            clauses, params = [], []
            for field, value in [('h.canonical_name', hospital), ('h.city', city), ('d.standard_name', specialty)]:
                if value:
                    clauses.append(f'{field} = ?')
                    params.append(' '.join(value.split()))
            ranking_columns = {row[1] for row in db.execute('PRAGMA table_info(hospital_rankings)')}
            source_columns = {row[1] for row in db.execute('PRAGMA table_info(ranking_sources)')}
            rank_level = 'hr.rank_level' if 'rank_level' in ranking_columns else 'NULL'
            rank_scope = 'hr.rank_scope' if 'rank_scope' in ranking_columns else 'NULL'
            rank_name = 'hr.ranking_name' if 'ranking_name' in ranking_columns else 'NULL'
            rank_year = 'hr.rank_year' if 'rank_year' in ranking_columns else 'NULL'
            source_url = 'hr.evidence_url' if 'evidence_url' in ranking_columns else 'rs.source_url'
            source_scope = 'rs.scope' if 'scope' in source_columns else "''"
            source_name = 'rs.name' if 'name' in source_columns else "''"
            source_publisher = 'rs.publisher' if 'publisher' in source_columns else "''"
            source_year = 'rs.edition_year' if 'edition_year' in source_columns else 'NULL'
            # Aggregate before applying the hospital/city filter. Computing a
            # window over the filtered rows makes each hospital look like the
            # last entry in its ranking list.
            ranking_max_status = (
                " AND COALESCE(hr_max.verification_status, 'verified') IN "
                "('verified', '\u5df2\u6838\u9a8c', '\u5df2\u901a\u8fc7')"
                if 'verification_status' in ranking_columns else ''
            )
            ranking_max_join = f'''
                LEFT JOIN (
                    SELECT ranking_source_id, COALESCE(specialty_id, '') AS specialty_key,
                           MAX(rank) AS ranking_max_rank
                    FROM hospital_rankings hr_max
                    WHERE rank IS NOT NULL{ranking_max_status}
                    GROUP BY ranking_source_id, COALESCE(specialty_id, '')
                ) ranking_max
                  ON ranking_max.ranking_source_id = hr.ranking_source_id
                 AND ranking_max.specialty_key = COALESCE(hr.specialty_id, '')
            '''
            if 'verification_status' in ranking_columns:
                clauses.append("COALESCE(hr.verification_status, 'verified') IN ('verified', '\u5df2\u6838\u9a8c', '\u5df2\u901a\u8fc7')")
            where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
            rows = db.execute(
                    f'''SELECT hr.id, h.canonical_name AS hospital, h.city,
                           COALESCE(d.standard_name, '') AS specialty,
                           hr.rank, ranking_max.ranking_max_rank,
                           hr.award_level AS tier,
                           COALESCE({rank_level}, {source_scope}, '') AS ranking_scope,
                           COALESCE({rank_scope}, {rank_name}, {source_name}, '') AS ranking_name,
                           COALESCE({source_name}, '') AS ranking_source_name,
                           COALESCE(NULLIF(hr.publisher, ''), {source_publisher}, '') AS ranking_publisher,
                           COALESCE({source_scope}, '') AS ranking_source_scope,
                           COALESCE({rank_year}, {source_year}) AS year,
                           COALESCE({source_url}, '') AS source, h.verification_status
                    FROM hospital_rankings hr
                    JOIN hospitals h ON h.hospital_id = hr.hospital_id
                     LEFT JOIN departments d ON d.department_id = hr.specialty_id
                     JOIN ranking_sources rs ON rs.ranking_source_id = hr.ranking_source_id
                     {ranking_max_join}
                     {where}
                    ORDER BY year DESC, hr.rank ASC''',
                params,
            ).fetchall()
            return [_normalize_ranking_record(dict(row)) for row in rows]
    initialize_ranking_store(path)
    clauses, params = [], []
    for field, value in [('hospital', hospital), ('city', city), ('specialty', specialty)]:
        if value:
            clauses.append(f'{field} = ?')
            params.append(' '.join(value.split()))
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
    with connect(path) as db:
        rows = db.execute(f'SELECT * FROM specialty_rankings{where} ORDER BY year DESC, rank ASC', params).fetchall()
        return [_normalize_ranking_record(dict(row)) for row in rows]


def ranking_records_for_hospitals(hospitals: Iterable[str], *, path: Path) -> dict[str, list[dict[str, object]]]:
    """Read all ranking evidence for a hospital set with one database query."""
    names = tuple(dict.fromkeys(' '.join(str(name).split()) for name in hospitals if str(name).strip()))
    if not names:
        return {}
    with connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if {'hospital_rankings', 'ranking_sources', 'hospitals'} <= tables:
            ranking_columns = {row[1] for row in db.execute('PRAGMA table_info(hospital_rankings)')}
            source_columns = {row[1] for row in db.execute('PRAGMA table_info(ranking_sources)')}
            rank_level = 'hr.rank_level' if 'rank_level' in ranking_columns else 'NULL'
            rank_scope = 'hr.rank_scope' if 'rank_scope' in ranking_columns else 'NULL'
            rank_name = 'hr.ranking_name' if 'ranking_name' in ranking_columns else 'NULL'
            rank_year = 'hr.rank_year' if 'rank_year' in ranking_columns else 'NULL'
            source_url = 'hr.evidence_url' if 'evidence_url' in ranking_columns else 'rs.source_url'
            source_scope = 'rs.scope' if 'scope' in source_columns else "''"
            source_name = 'rs.name' if 'name' in source_columns else "''"
            source_publisher = 'rs.publisher' if 'publisher' in source_columns else "''"
            source_year = 'rs.edition_year' if 'edition_year' in source_columns else 'NULL'
            ranking_max_status = (
                " AND COALESCE(hr_max.verification_status, 'verified') IN ('verified', '已核验', '已通过')"
                if 'verification_status' in ranking_columns else ''
            )
            ranking_max_join = f'''
                LEFT JOIN (
                    SELECT ranking_source_id, COALESCE(specialty_id, '') AS specialty_key,
                           MAX(rank) AS ranking_max_rank
                    FROM hospital_rankings hr_max
                    WHERE rank IS NOT NULL{ranking_max_status}
                    GROUP BY ranking_source_id, COALESCE(specialty_id, '')
                ) ranking_max
                  ON ranking_max.ranking_source_id = hr.ranking_source_id
                 AND ranking_max.specialty_key = COALESCE(hr.specialty_id, '')
            '''
            verification_clause = (
                " AND COALESCE(hr.verification_status, 'verified') IN ('verified', '已核验', '已通过')"
                if 'verification_status' in ranking_columns else ''
            )
            placeholders = ', '.join('?' for _ in names)
            rows = db.execute(
                f'''SELECT hr.id, h.canonical_name AS hospital, h.city,
                           COALESCE(d.standard_name, '') AS specialty,
                           hr.rank, ranking_max.ranking_max_rank,
                           hr.award_level AS tier,
                           COALESCE({rank_level}, {source_scope}, '') AS ranking_scope,
                           COALESCE({rank_scope}, {rank_name}, {source_name}, '') AS ranking_name,
                           COALESCE({source_name}, '') AS ranking_source_name,
                           COALESCE(NULLIF(hr.publisher, ''), {source_publisher}, '') AS ranking_publisher,
                           COALESCE({source_scope}, '') AS ranking_source_scope,
                           COALESCE({rank_year}, {source_year}) AS year,
                           COALESCE({source_url}, '') AS source, h.verification_status
                    FROM hospital_rankings hr
                    JOIN hospitals h ON h.hospital_id = hr.hospital_id
                    LEFT JOIN departments d ON d.department_id = hr.specialty_id
                    JOIN ranking_sources rs ON rs.ranking_source_id = hr.ranking_source_id
                    {ranking_max_join}
                    WHERE h.canonical_name IN ({placeholders}){verification_clause}
                    ORDER BY year DESC, hr.rank ASC''',
                names,
            ).fetchall()
        else:
            initialize_ranking_store(path)
            placeholders = ', '.join('?' for _ in names)
            rows = db.execute(
                f'SELECT * FROM specialty_rankings WHERE hospital IN ({placeholders}) ORDER BY year DESC, rank ASC',
                names,
            ).fetchall()
    grouped: dict[str, list[dict[str, object]]] = {name: [] for name in names}
    for row in rows:
        record = _normalize_ranking_record(dict(row))
        grouped.setdefault(str(record.get('hospital') or '').strip(), []).append(record)
    return grouped


def credential_records(*, hospital_id: str = '', hospital: str = '', specialty: str = '', path: Path) -> list[dict[str, object]]:
    """Read verified hospital/specialty credentials when the optional table exists."""
    with connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'hospital_credentials' not in tables:
            return []
        columns = {row[1] for row in db.execute('PRAGMA table_info(hospital_credentials)')}
        if not {'hospital_id', 'credential_name', 'credential_level'} <= columns:
            return []
        clauses: list[str] = []
        params: list[object] = []
        if hospital_id:
            clauses.append('hc.hospital_id = ?')
            params.append(hospital_id)
        if hospital:
            clauses.append('h.canonical_name = ?')
            params.append(' '.join(hospital.split()))
        department_column = 'department_id' if 'department_id' in columns else ('dept_id' if 'dept_id' in columns else '')
        updated_column = 'retrieved_at' if 'retrieved_at' in columns else ('data_updated_at' if 'data_updated_at' in columns else '')
        if specialty and 'departments' in tables and department_column:
            clauses.append(f'(d.standard_name = ? OR hc.{department_column} IS NULL)')
            params.append(' '.join(specialty.split()))
        if 'verification_status' in columns:
            clauses.append("hc.verification_status IN ('verified', '已核验', '已通过')")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ''
        join_department = f'LEFT JOIN departments d ON d.department_id = hc.{department_column}' if 'departments' in tables and department_column else ''
        updated_select = f'hc.{updated_column}' if updated_column else 'NULL'
        rows = db.execute(
            f'''SELECT hc.hospital_id, COALESCE(d.standard_name, '') AS specialty,
                       hc.credential_name, hc.credential_level, hc.issuing_body,
                       hc.issue_year, hc.evidence_url, {updated_select} AS data_updated_at
                FROM hospital_credentials hc
                LEFT JOIN hospitals h ON h.hospital_id = hc.hospital_id
                {join_department}{where}
                ORDER BY CASE hc.credential_level WHEN '国家级' THEN 1 WHEN '省级' THEN 2 WHEN '市级' THEN 3 ELSE 4 END,
                         hc.issue_year DESC''',
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def credential_records_for_hospitals(
    hospital_ids: Iterable[str],
    specialties: Iterable[str],
    *,
    path: Path,
) -> dict[str, list[dict[str, object]]]:
    """Read verified credentials for many hospitals and directions in one query."""
    ids = tuple(dict.fromkeys(str(value).strip() for value in hospital_ids if str(value).strip()))
    directions = tuple(dict.fromkeys(' '.join(str(value).split()) for value in specialties if str(value).strip()))
    if not ids:
        return {}
    with connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'hospital_credentials' not in tables:
            return {hospital_id: [] for hospital_id in ids}
        columns = {row[1] for row in db.execute('PRAGMA table_info(hospital_credentials)')}
        if not {'hospital_id', 'credential_name', 'credential_level'} <= columns:
            return {hospital_id: [] for hospital_id in ids}
        department_column = 'department_id' if 'department_id' in columns else ('dept_id' if 'dept_id' in columns else '')
        updated_column = 'retrieved_at' if 'retrieved_at' in columns else ('data_updated_at' if 'data_updated_at' in columns else '')
        id_placeholders = ', '.join('?' for _ in ids)
        clauses = [f'hc.hospital_id IN ({id_placeholders})']
        params: list[object] = list(ids)
        if directions and 'departments' in tables and department_column:
            specialty_placeholders = ', '.join('?' for _ in directions)
            clauses.append(f'(d.standard_name IN ({specialty_placeholders}) OR hc.{department_column} IS NULL)')
            params.extend(directions)
        if 'verification_status' in columns:
            clauses.append("hc.verification_status IN ('verified', '已核验', '已通过')")
        join_department = f'LEFT JOIN departments d ON d.department_id = hc.{department_column}' if 'departments' in tables and department_column else ''
        updated_select = f'hc.{updated_column}' if updated_column else 'NULL'
        rows = db.execute(
            f'''SELECT hc.hospital_id, COALESCE(d.standard_name, '') AS specialty,
                       hc.credential_name, hc.credential_level, hc.issuing_body,
                       hc.issue_year, hc.evidence_url, {updated_select} AS data_updated_at
                FROM hospital_credentials hc
                {join_department}
                WHERE {' AND '.join(clauses)}
                ORDER BY CASE hc.credential_level WHEN '国家级' THEN 1 WHEN '省级' THEN 2 WHEN '市级' THEN 3 ELSE 4 END,
                         hc.issue_year DESC''',
            params,
        ).fetchall()
    grouped: dict[str, list[dict[str, object]]] = {hospital_id: [] for hospital_id in ids}
    for row in rows:
        record = dict(row)
        grouped.setdefault(str(record.get('hospital_id') or '').strip(), []).append(record)
    return grouped


def _optional_int(value: object) -> int | None:
    if value in (None, ''):
        return None
    return int(value)


def _normalize_ranking_record(record: dict[str, object]) -> dict[str, object]:
    """Return a ranking record with a currently valid public source entry point.

    The ranking site retired the old year-specific specialty route, while the
    underlying ranking evidence remains valid. Keep the stored ranking data
    intact and only normalize the URL exposed to the client.
    """
    source = str(record.get('source') or '').strip()
    parsed = urlparse(source)
    if parsed.scheme == 'https' and parsed.netloc == 'rank.cn-healthcare.com':
        replacement_path = None
        if parsed.path.startswith('/fudan/national-specialty/year/'):
            replacement_path = '/fudan/specialty-reputation'
        elif parsed.path.startswith('/fudan/national-general/year/'):
            replacement_path = '/fudan/national-general'
        if replacement_path:
            record['source'] = urlunparse((parsed.scheme, parsed.netloc, replacement_path, '', '', ''))
    return record
