import logging
import csv
from io import StringIO
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.ai_matcher import ai_match
from app.matcher import is_public_record, match
from app.data import verified_row_to_hospital
from app.importer import load_verified_beijing_rows
from app.importer import validate_import
from app.schemas import AIMatchRequest, MatchRequest

logger = logging.getLogger(__name__)
app = FastAPI()
IMPORT_COLUMNS = (
    'id', 'name', 'city', 'tier', 'source_url', 'source_date',
    'specialties', 'disease_tags', 'verified', 'published',
)
MAX_IMPORT_PREVIEW_BYTES = 1024 * 1024
VERIFIED_BEIJING_PUBLISH_LIST_PATH = Path(__file__).parent / 'data' / 'verified_beijing_hospitals.csv'
PUBLIC_HOSPITALS = tuple(
    verified_row_to_hospital(row)
    for row in load_verified_beijing_rows(VERIFIED_BEIJING_PUBLISH_LIST_PATH, date.today())
)


def current_date() -> date:
    """Clock boundary for source-freshness checks."""
    return date.today()


@app.middleware('http')
async def log_request(request: Request, call_next):
    request_id = str(uuid4())
    response = await call_next(request)
    response.headers['X-Request-ID'] = request_id
    logger.info(
        'request method=%s path=%s status=%s request_id=%s',
        request.method,
        request.url.path,
        response.status_code,
        request_id,
    )
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={'code': 'INVALID_REQUEST'})


@app.get('/health')
async def health():
    return {'status': 'ok'}


@app.post('/admin/import-preview')
async def import_preview(request: Request, as_of: date = Depends(current_date)):
    """Validate a CSV upload in memory without publishing or retaining it."""
    content = await request.body()
    if len(content) > MAX_IMPORT_PREVIEW_BYTES:
        raise HTTPException(status_code=400, detail='Import preview payload exceeds 1 MB')
    try:
        reader = csv.DictReader(StringIO(content.decode('utf-8')))
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail='Import preview must be UTF-8 CSV') from None

    headers = reader.fieldnames or []
    missing_headers = [column for column in IMPORT_COLUMNS if column not in headers]
    unknown_headers = [header for header in headers if header not in IMPORT_COLUMNS]
    if missing_headers or unknown_headers:
        errors = [
            {'row': 1, 'fields': [column], 'error': 'Missing documented CSV header'}
            for column in missing_headers
        ]
        errors.extend(
            {'row': 1, 'fields': [header], 'error': 'Unknown CSV header'}
            for header in unknown_headers
        )
        return JSONResponse(status_code=400, content={'accepted_count': 0, 'errors': errors})

    rows = [
        {column: (raw.get(column) or '') for column in IMPORT_COLUMNS}
        for raw in reader
    ]
    report = validate_import(rows, as_of)
    errors = [
        {'row': error.row_number + 1, 'fields': list(error.fields), 'error': 'Validation failed'}
        for error in report.errors
    ]
    if not rows:
        errors.append({'row': 1, 'fields': list(IMPORT_COLUMNS), 'error': 'Validation failed'})
    return {'accepted_count': len(report.accepted), 'errors': errors}


@app.post('/v1/matches')
async def matches(request: MatchRequest, as_of: date = Depends(current_date)):
    return match(request.query, request.city, request.priority, hospitals=PUBLIC_HOSPITALS, as_of=as_of)


@app.post('/v1/ai-matches')
async def ai_matches(request: AIMatchRequest, as_of: date = Depends(current_date)):
    return ai_match(
        request.query,
        request.city,
        request.priority,
        request.ai_consent,
        hospitals=PUBLIC_HOSPITALS,
        as_of=as_of,
    )


@app.get('/v1/hospitals/{hospital_id}')
async def hospital_detail(hospital_id: str, as_of: date = Depends(current_date)):
    hospital = next(
        (
            item
            for item in PUBLIC_HOSPITALS
            if item.id == hospital_id and is_public_record(item, as_of=as_of)
        ),
        None,
    )
    if hospital is None:
        raise HTTPException(status_code=404, detail='Hospital not found')

    return {
        'id': hospital.id,
        'name': hospital.name,
        'city': hospital.city,
        'specialties': list(hospital.specialties),
        'source': {
            'label': hospital.demo_label,
            'date': hospital.source_date.isoformat(),
        },
    }
