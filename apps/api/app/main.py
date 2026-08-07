import logging
import csv
from io import StringIO
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.ai_matcher import AIMatchResponse, ai_match
from app.matcher import is_public_record, match
from app.data import verified_row_to_hospital
from app.importer import load_verified_beijing_rows
from app.importer import validate_import
from app.schemas import AIMatchRequest, MatchRequest, RealtimeSearchRequest
from app.bocha_search import BochaSearchClient
from app.realtime_search import candidate_from_document, merge_hospital_candidates, rank_candidates
from app.web_ranker import synthesize_hospital_results

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
REALTIME_DETAIL_SESSIONS: dict[str, tuple[datetime, dict[str, object]]] = {}
REALTIME_DETAIL_TTL = timedelta(minutes=15)

_SEARCH_CITY_NAMES = {
    '广州': 'Guangzhou', '广州市': 'Guangzhou', '深圳': 'Shenzhen', '深圳市': 'Shenzhen',
    '北京': 'Beijing', '北京市': 'Beijing', '上海': 'Shanghai', '上海市': 'Shanghai',
    '杭州': 'Hangzhou', '杭州市': 'Hangzhou', '成都': 'Chengdu', '成都市': 'Chengdu',
    '武汉': 'Wuhan', '武汉市': 'Wuhan', '南京': 'Nanjing', '南京市': 'Nanjing',
    '天津': 'Tianjin', '天津市': 'Tianjin', '重庆': 'Chongqing', '重庆市': 'Chongqing',
}
_SEARCH_DIRECTION_NAMES = {
    '心血管内科': 'cardiology', '呼吸内科': 'respiratory medicine', '神经内科': 'neurology',
    '肿瘤科': 'oncology', '骨科': 'orthopedics', '妇产科': 'obstetrics gynecology',
    '儿科': 'pediatrics', '眼科': 'ophthalmology', '耳鼻咽喉头颈外科': 'otolaryngology',
    '消化内科': 'gastroenterology', '内分泌科': 'endocrinology', '皮肤科': 'dermatology',
}
_SEARCH_SYMPTOM_NAMES = {
    '心绞痛': 'angina heart disease cardiology', '冠心病': 'coronary heart disease cardiology',
    '胸痛': 'chest pain cardiology', '心肌梗死': 'myocardial infarction cardiology',
    '心肌缺血': 'ischemic heart disease cardiology', '发热': 'fever infectious disease',
    '咳嗽': 'cough respiratory medicine', '关节疼痛': 'joint pain orthopedics',
}


def _bocha_query_terms(request: RealtimeSearchRequest, directions: list[str]) -> tuple[str, ...]:
    city = _SEARCH_CITY_NAMES.get(request.location.city, '')
    direction_terms = [_SEARCH_DIRECTION_NAMES.get(direction, '') for direction in directions]
    direction_terms = [term for term in direction_terms if term]
    symptom_term = ' '.join(direction_terms) or next(
        (value for key, value in _SEARCH_SYMPTOM_NAMES.items() if key in request.query),
        'medical specialty',
    )
    place_term = city or 'China'
    return place_term, symptom_term


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


@app.post('/v1/ai-matches', response_model=AIMatchResponse)
async def ai_matches(request: AIMatchRequest, as_of: date = Depends(current_date)):
    return await run_in_threadpool(
        ai_match,
        request.query,
        request.city,
        request.priority,
        request.ai_consent,
        hospitals=PUBLIC_HOSPITALS,
        as_of=as_of,
    )


@app.post('/v1/realtime-hospital-search')
async def realtime_hospital_search(request: RealtimeSearchRequest):
    """Search public web sources and return up to ten explainable results."""
    # Run the deterministic emergency classifier before any external call.
    local = match(request.query, request.location.city, 'overall')
    if local.emergency:
        return {
            'status': 'EMERGENCY',
            'directions': [],
            'scope': request.scope,
            'results': [],
            'sources': [],
            'fetched_at': None,
        }

    directions = list(local.directions)
    # ai_match owns the DeepSeek consent/key gate. It is never invoked for an
    # unconsented request, which keeps symptom text out of the AI transport.
    if request.ai_consent:
        ai_response = await run_in_threadpool(
            ai_match,
            request.query,
            request.location.city,
            'overall',
            True,
            hospitals=PUBLIC_HOSPITALS,
        )
        directions = list(dict.fromkeys(ai_response.directions or directions))

    search_client = BochaSearchClient()
    place_term, specialty_term = _bocha_query_terms(request, directions)
    search_queries = [
        f'{place_term} {specialty_term} hospital official website',
        f'{place_term} {specialty_term} top hospital',
        f'{place_term} hospital {specialty_term} department',
        f'China {specialty_term} hospital official website',
        f'{request.location.city} {request.query} 医院 排名',
        f'{request.location.city} {" ".join(directions)} 医院 官方',
        f'{request.location.city} 三甲 {" ".join(directions)} 医院',
        f'{request.location.city} 心脏中心 医院 官方',
    ]
    search_results = [
        await run_in_threadpool(search_client.search, query, 10)
        for query in dict.fromkeys(search_queries)
    ]
    if not any(result.available for result in search_results):
        return {
            'status': 'SEARCH_UNAVAILABLE',
            'directions': directions,
            'scope': request.scope,
            'results': [],
            'sources': [],
            'fetched_at': None,
        }

    documents = [document for result in search_results for document in result.documents]
    candidates = [
        candidate
        for document in documents
        if (candidate := candidate_from_document(
            document,
            location=request.location,
            require_location_evidence=request.scope in {'district', 'city'},
        )) is not None
    ]
    candidates = merge_hospital_candidates(candidates)
    results = rank_candidates(
        candidates,
        directions=directions,
        location=request.location,
        scope=request.scope,
    )
    synthesized = synthesize_hospital_results(
        query=request.query,
        location=request.location.model_dump(),
        directions=directions,
        results=results,
    ) if request.ai_consent else None
    if synthesized is not None:
        results = synthesized
    if not results:
        return {
            'status': 'NO_RESULTS',
            'directions': directions,
            'scope': request.scope,
            'results': [],
            'sources': [],
            'fetched_at': None,
        }
    sources = list(dict.fromkeys(url for result in results for url in result['source_urls']))
    fetched_at = max(result['fetched_at'] for result in results)
    now = datetime.now(UTC)
    for result in results[:10]:
        REALTIME_DETAIL_SESSIONS[str(result['id'])] = (now, {
            'id': result['id'],
            'name': result['name'],
            'city': result['city'],
            'address': result.get('address') or result['city'],
            'department': result.get('department') or ('、'.join(directions)),
            'introduction': next((source['snippet'] for source in result['sources'] if source['snippet']), None),
            'departments': list(directions),
            'doctors': [],
            'registration_url': result['registration_url'],
            'sources': result['sources'],
            'fetched_at': result['fetched_at'],
        })
    return {
        'status': 'OK',
        'directions': directions,
        'scope': request.scope,
        'results': results[:10],
        'sources': sources,
        'fetched_at': fetched_at,
    }


@app.get('/v1/realtime-hospitals/{hospital_id}')
async def realtime_hospital_detail(hospital_id: str):
    session = REALTIME_DETAIL_SESSIONS.get(hospital_id)
    if session is None:
        raise HTTPException(status_code=404, detail='Realtime hospital result not found')
    created_at, detail = session
    if datetime.now(UTC) - created_at > REALTIME_DETAIL_TTL:
        REALTIME_DETAIL_SESSIONS.pop(hospital_id, None)
        raise HTTPException(status_code=404, detail='Realtime hospital result expired')
    return detail


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
