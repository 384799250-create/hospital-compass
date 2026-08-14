import logging
import csv
import os
import json
import hashlib
from io import StringIO
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

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
from app.anysearch import AnySearchClient, prefer_search_result
from app.realtime_search import _expanded_specialty_terms, candidate_from_document, merge_hospital_candidates, normalize_hospital_name, rank_candidates
from app import web_ranker
from app.web_ranker import synthesize_hospital_results
from app.hospital_store import initialize as initialize_hospital_store
from app.hospital_store import directory_rows
from app.tertiary_store import tertiary_rows, tertiary_database_path
from app.hospital_store import database_path
from app.specialty_ranking_store import credential_records, ranking_records
from app.search_policy import HourlySearchBudget, SearchCache, compact_search_queries
from app.disease_profiles import profile_for_query
from app.triage import TriageResponse, triage_symptoms
from app.symptom_clarification import ClarificationUnavailableError, clarify_symptoms
from app.bocha_search import BochaSearchClient, SearchDocument
from app.realtime_search import HospitalCandidate

logger = logging.getLogger(__name__)
app = FastAPI()
HOSPITAL_DIRECTORY_PATH = initialize_hospital_store()
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
REALTIME_SEARCH_CACHE = SearchCache(ttl=timedelta(minutes=30))
REALTIME_SEARCH_BUDGET = HourlySearchBudget(
    limit=int(os.environ.get('BOCHA_MAX_CALLS_PER_HOUR', '60')),
)


def _directory_fallback_candidates(request: RealtimeSearchRequest) -> list[HospitalCandidate]:
    province = request.location.province if request.scope != 'national' else ''
    city = request.location.city if request.scope in {'city', 'district'} else ''
    district = request.location.district if request.scope == 'district' else ''
    rows = tertiary_rows(province=province, city=city, district=district)
    candidates: list[HospitalCandidate] = []
    for row in rows:
        name = str(row.get('canonical_name') or '').strip()
        address = str(row.get('address') or '').strip()
        if not name or not address:
            continue
        try:
            fetched_at = datetime.fromisoformat(str(row.get('source_updated_at') or row.get('updated_at') or '')).replace(tzinfo=UTC)
        except ValueError:
            fetched_at = datetime.now(UTC)
        source = SearchDocument(
            title=name,
            url='https://y.dxy.cn/hospital/',
            snippet=f'{address}；{row.get("tier") or ""}',
            fetched_at=fetched_at,
        )
        try:
            specialties = tuple(json.loads(str(row.get('specialties_json') or '[]')))
        except (TypeError, json.JSONDecodeError):
            specialties = ()
        capabilities = tuple(
            item for item in (row.get('specialty_capabilities') or ())
            if str(item.get('strength_level') or '').strip() not in {'待核验', '未核验', ''}
            and '相关疾病' not in str(item.get('diagnosis_scope') or '')
        )
        if not specialties:
            specialties = tuple(dict.fromkeys(
                str(item.get('department') or '').strip()
                for item in capabilities
                if item.get('department')
            ))
        candidates.append(HospitalCandidate(
            name=name,
            city=str(row.get('city') or request.location.city),
            address=address,
            core_advantages='',
            province=str(row.get('province') or request.location.province),
            district=str(row.get('district') or request.location.district),
            specialties=specialties,
            tier=str(row.get('tier') or ''),
            capability_evidence=capabilities,
            registration_url=_safe_http_url(row.get('registration_url')),
            official_website_url=_safe_http_url(row.get('official_domain'), add_scheme=True),
            sources=[source],
            public_capability=78.0 if '三级甲等' in str(row.get('tier') or '') else 50.0,
        ))
    return candidates


def _safe_http_url(value: object, *, add_scheme: bool = False) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    if add_scheme and '://' not in text:
        text = f'https://{text}'
    parsed = urlparse(text)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return text


def _attach_ranking_evidence(candidates: list[HospitalCandidate], directions: list[str]) -> list[HospitalCandidate]:
    """Attach stored authoritative evidence without changing candidate identity."""
    database_rows = tertiary_rows()
    enriched: list[HospitalCandidate] = []
    for candidate in candidates:
        normalized_name = normalize_hospital_name(candidate.name)
        base_name = normalized_name.split('（', 1)[0].split('(', 1)[0].strip()
        names = tuple(dict.fromkeys((candidate.name, normalized_name, base_name)))
        matching_rows = [
            row for row in database_rows
            if normalize_hospital_name(str(row.get('canonical_name') or '')) in names
        ]
        # The local directory is authoritative for identity and location. A
        # search result often falls back to the requested city when its page
        # omits location metadata, so city must not be used to reject an exact
        # hospital-name match.
        database_row = next(
            (row for row in matching_rows if str(row.get('city') or '').strip() == candidate.city),
            None,
        ) or (matching_rows[0] if matching_rows else None)
        database_address = str(database_row.get('address') or '').strip() if database_row else ''
        current_address = str(candidate.address or '').strip()
        if database_row:
            candidate = HospitalCandidate(**{
                **candidate.__dict__,
                'province': str(database_row.get('province') or candidate.province or '').strip(),
                'city': str(database_row.get('city') or candidate.city or '').strip(),
                'district': str(database_row.get('district') or candidate.district or '').strip(),
                'address': database_address or current_address,
                'registration_url': (
                    str(database_row.get('registration_url') or '').strip()
                    or candidate.registration_url
                ) or None,
                'official_website_url': _safe_http_url(database_row.get('official_domain'), add_scheme=True)
                or candidate.official_website_url,
            })
        rows = []
        for name in names:
            rows.extend(ranking_records(hospital=name, path=database_path()))
        city_rows = [row for row in rows if row.get('city') in {candidate.city, '全国'}]
        rows = city_rows or rows
        if directions:
            terms = tuple(term.casefold() for direction in directions for term in _expanded_specialty_terms(direction))
            matched = [
                row for row in rows
                if any(
                    term in str(row.get('specialty') or '').casefold()
                    or str(row.get('specialty') or '').casefold() in term
                    for term in terms
                )
            ]
            general = [row for row in rows if not str(row.get('specialty') or '').strip()]
            rows = matched + general
        evidence = tuple({
            **row,
            'ranking_scope': row.get('ranking_scope') or row.get('scope') or row.get('ranking_name') or '',
            'score': float(max(0, 100 - (int(row['rank']) - 1) * 3)) if row.get('rank') else 0.0,
        } for row in rows[:5])
        credentials = []
        if database_row and database_row.get('id'):
            for direction in directions:
                credentials.extend(credential_records(
                    hospital_id=str(database_row['id']),
                    specialty=direction,
                    path=database_path(),
                ))
        credential_evidence = tuple({
            'department': str(item.get('specialty') or '').strip(),
            'strength_level': str(item.get('credential_level') or '').strip(),
            'diagnosis_scope': str(item.get('credential_name') or '').strip(),
            'credential_name': str(item.get('credential_name') or '').strip(),
            'source': str(item.get('evidence_url') or '').strip(),
            'year': item.get('issue_year'),
            'verification_status': '已核验' if item.get('credential_level') else '待核验',
        } for item in credentials if item.get('credential_name'))
        enriched.append(HospitalCandidate(**{
            **candidate.__dict__,
            'ranking_evidence': evidence,
            # Prefer verified database credentials so the client shows their
            # issue year and evidence URL before generic search-page claims.
            'capability_evidence': credential_evidence + candidate.capability_evidence,
        }))
    return enriched


def _build_local_results(
    request: RealtimeSearchRequest,
    directions: list[str],
    profile_key: str,
) -> tuple[list[HospitalCandidate], list[dict[str, object]]]:
    candidates = _attach_ranking_evidence(
        merge_hospital_candidates(_directory_fallback_candidates(request)), directions,
    )
    results = rank_candidates(
        candidates,
        directions=directions,
        location=request.location,
        location_level=request.location_level,
        scope=request.scope,
        profile_key=profile_key,
    )
    return candidates, results


async def _cached_external_search(
    search_client: AnySearchClient,
    query: str,
    fallback_client: BochaSearchClient | None = None,
):
    cached = REALTIME_SEARCH_CACHE.get(query)
    if cached is not None:
        return cached
    if not REALTIME_SEARCH_BUDGET.allow():
        return None
    result = await run_in_threadpool(search_client.search, query, 10)
    REALTIME_SEARCH_BUDGET.record()
    if result.available and result.documents:
        REALTIME_SEARCH_CACHE.set(query, result)

    # Bocha is an opt-in fallback: it is consulted only when AnySearch is
    # unavailable or returned no documents, so normal requests make one call.
    if result.available and result.documents:
        return result
    if fallback_client is None or not os.environ.get('BOCHA_API_KEY'):
        return result
    if not REALTIME_SEARCH_BUDGET.allow():
        return result
    fallback = await run_in_threadpool(fallback_client.search, query, 10)
    REALTIME_SEARCH_BUDGET.record()
    selected = prefer_search_result(result, fallback)
    if selected.available and selected.documents:
        REALTIME_SEARCH_CACHE.set(query, selected)
    return selected


REALTIME_DETAIL_TTL = timedelta(minutes=15)
_WIDER_SCOPE = {'district': 'city', 'city': 'province', 'province': 'national'}

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


@app.post('/v1/triage', response_model=TriageResponse)
async def triage(request: AIMatchRequest):
    if not request.ai_consent:
        raise HTTPException(status_code=400, detail='AI consent is required before triage')
    return await run_in_threadpool(triage_symptoms, request.query, request.ai_consent)


@app.post('/v1/symptom-clarification')
async def symptom_clarification(request: dict[str, object]):
    if request.get('ai_consent') is not True:
        raise HTTPException(status_code=400, detail='AI consent is required before clarification')
    try:
        return await run_in_threadpool(
            clarify_symptoms,
            str(request.get('query') or ''),
            answers=list(request.get('answers') or []),
            ai_consent=True,
            environ=os.environ,
        )
    except ClarificationUnavailableError as exc:
        raise HTTPException(status_code=503, detail='AI clarification is temporarily unavailable') from exc


@app.post('/v1/realtime-hospital-search')
async def realtime_hospital_search(request: RealtimeSearchRequest):
    """Search public web sources and return up to ten explainable results."""
    # Run the deterministic emergency classifier before any external call.
    local = match(request.query, request.location.city, 'overall')
    if local.emergency:
        return {
            'status': 'EMERGENCY',
            'search_mode': '本地规则',
            'directions': [],
            'scope': request.scope,
            'results': [],
            'sources': [],
            'fetched_at': None,
        }

    directions = [request.confirmed_direction] if request.confirmed_direction else list(local.directions)
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

    profile_key = profile_for_query(request.query).key

    local_candidates, local_results = await run_in_threadpool(
        _build_local_results, request, directions, profile_key,
    )
    search_client = AnySearchClient()
    fallback_client = BochaSearchClient() if os.environ.get('BOCHA_API_KEY') else None
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
        f'{request.location.city} 省人民医院 {specialty_term} 官方',
        f'{request.location.city} 市人民医院 {specialty_term} 官方',
        f'{request.location.city} 国家区域医疗中心 {specialty_term}',
        f'{request.location.city} {request.query} 医院 官方 挂号',
    ]
    if len(local_results) >= 10:
        # Local coverage is not proof that recall is complete. Keep one
        # low-cost web recall query to discover newer or omitted hospitals.
        search_queries = (f'{place_term} {specialty_term} hospital official website',)
    else:
        place_term, specialty_term = _bocha_query_terms(request, directions)
        search_queries = compact_search_queries(request.location.city or place_term, specialty_term, request.query)
    search_results = []
    for query in search_queries:
        result = await _cached_external_search(search_client, query, fallback_client)
        if result is not None:
            search_results.append(result)
    if search_results and not any(result.available for result in search_results) and not local_results:
        return {
            'status': 'SEARCH_UNAVAILABLE',
            'search_mode': '本地资料',
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
            require_district_evidence=request.scope == 'district',
        )) is not None
    ]
    tertiary_names = {normalize_hospital_name(str(row.get('canonical_name') or '')) for row in tertiary_rows()}
    candidates = [candidate for candidate in candidates if normalize_hospital_name(candidate.name) in tertiary_names]
    candidates = await run_in_threadpool(
        lambda: _attach_ranking_evidence(merge_hospital_candidates(candidates), directions),
    )
    if len(candidates) < 10:
        candidates.extend(local_candidates)
        candidates = merge_hospital_candidates(candidates)
    results = await run_in_threadpool(
        rank_candidates,
        candidates,
        directions=directions,
        location=request.location,
        location_level=request.location_level,
        scope=request.scope,
        profile_key=profile_key,
    )
    synthesized = await run_in_threadpool(
        synthesize_hospital_results,
        query=request.query,
        location=request.location.model_dump(),
        directions=directions,
        results=results,
    ) if request.ai_consent else None
    processing_notice = None
    if request.ai_consent and synthesized is None:
        failure_reason = web_ranker.LAST_SYNTHESIS_FAILURE or 'unknown'
        processing_notice = (
            f'模型整理未成功（{failure_reason}），当前展示程序模板整理结果。请稍后重试。'
            if os.environ.get('DEEPSEEK_API_KEY')
            else '当前未检测到 DeepSeek 服务配置，当前展示程序模板整理结果。'
        )
    if synthesized is not None:
        results = synthesized
    # Keep verified hospital website data attached after optional result
    # synthesis. The model may omit fields that are not part of its prose.
    database_rows = tertiary_rows()
    for result in results:
        result_name = normalize_hospital_name(str(result.get('name') or ''))
        database_row = next(
            (row for row in database_rows if normalize_hospital_name(str(row.get('canonical_name') or '')) == result_name),
            None,
        )
        if database_row:
            result['official_website_url'] = (
                result.get('official_website_url')
                or _safe_http_url(database_row.get('official_domain'), add_scheme=True)
            )
            result['wechat_appointment'] = result.get('wechat_appointment') or f"{result.get('name')}公众号"
    if not results:
        return {
            'status': 'NO_RESULTS',
            'search_mode': '本地资料+联网补充',
            'directions': directions,
            'scope': request.scope,
            'results': [],
            'sources': [],
            'fetched_at': None,
            'fallback_scope': _WIDER_SCOPE.get(request.scope),
            'fallback_message': '当前区域暂无足够医院资料，可切换更高一级区域查看。' if request.scope != 'national' else None,
        }
    sources = list(dict.fromkeys(url for result in results for url in result['source_urls']))
    fetched_at = max(result['fetched_at'] for result in results)
    now = datetime.now(UTC)
    database_rows = tertiary_rows()
    for result in results[:10]:
        database_row = next(
            (
                row for row in database_rows
                if normalize_hospital_name(str(row.get('canonical_name') or '')) == normalize_hospital_name(str(result['name'] or ''))
                and str(row.get('city') or '').strip() == str(result.get('city') or '').strip()
            ),
            None,
        )
        database_introduction = str(database_row.get('introduction') or '').strip() if database_row else ''
        official_website_url = _safe_http_url(database_row.get('official_domain'), add_scheme=True) if database_row else None
        REALTIME_DETAIL_SESSIONS[str(result['id'])] = (now, {
            'id': result['id'],
            'name': result['name'],
            'city': result['city'],
            'address': result.get('address') or result['city'],
            'department': result.get('department') or ('、'.join(directions)),
            'introduction': database_introduction or next((source['snippet'] for source in result['sources'] if source['snippet']), None),
            'departments': list(directions),
            'doctors': [],
            'registration_url': result['registration_url'],
            'official_website_url': official_website_url,
            'wechat_appointment': f"{result['name']}公众号",
            'sources': result['sources'],
            'fetched_at': result['fetched_at'],
        })
    return {
        'status': 'OK',
        'search_mode': '本地资料+联网补充' if search_results else '本地资料',
        'directions': directions,
        'scope': request.scope,
        'results': results[:10],
        'sources': sources,
        'fetched_at': fetched_at,
        'fallback_scope': _WIDER_SCOPE.get(request.scope) if len(results) < 10 else None,
        'fallback_message': '当前区域医院较少，可切换更高一级区域查看。' if len(results) < 10 and request.scope != 'national' else None,
        'processing_notice': processing_notice,
    }


@app.get('/v1/realtime-hospitals/{hospital_id}')
async def realtime_hospital_detail(hospital_id: str):
    session = REALTIME_DETAIL_SESSIONS.get(hospital_id)
    if session is None:
        for row in tertiary_rows():
            name = str(row.get('canonical_name') or '').strip()
            city = str(row.get('city') or '').strip()
            if hashlib.sha256(f'{name}|{city}'.encode()).hexdigest()[:16] != hospital_id:
                continue
            capabilities = tuple(row.get('specialty_capabilities') or ())
            departments = list(dict.fromkeys(
                str(item.get('department') or '').strip()
                for item in capabilities
                if item.get('department')
            ))
            address = str(row.get('address') or '').strip()
            introduction = str(row.get('introduction') or '').strip()
            official_website_url = _safe_http_url(row.get('official_domain'), add_scheme=True)
            return {
                'id': hospital_id,
                'name': name,
                'city': city,
                'address': address,
                'department': '、'.join(departments),
                'introduction': introduction or (f'{address}；{row.get("tier") or "三级甲等"}' if address else None),
                'departments': departments,
                'doctors': [],
                'registration_url': row.get('registration_url') or None,
                'official_website_url': official_website_url,
                'wechat_appointment': f"{name}公众号",
                'sources': [{
                    'title': name,
                    'url': 'https://y.dxy.cn/hospital/',
                    'snippet': f'{address}；{row.get("tier") or "三级甲等"}',
                    'fetched_at': row.get('source_updated_at') or row.get('updated_at') or datetime.now(UTC).isoformat(),
                }],
                'fetched_at': row.get('source_updated_at') or row.get('updated_at') or datetime.now(UTC).isoformat(),
            }
    if session is None:
        raise HTTPException(status_code=404, detail='Realtime hospital result not found')
    created_at, detail = session
    if datetime.now(UTC) - created_at > REALTIME_DETAIL_TTL:
        REALTIME_DETAIL_SESSIONS.pop(hospital_id, None)
        raise HTTPException(status_code=404, detail='Realtime hospital result expired')
    # Search providers often return only a city. Prefer the verified database
    # address when the session detail is incomplete or only repeats the city.
    enriched_detail = dict(detail)
    for row in tertiary_rows():
        name = str(row.get('canonical_name') or '').strip()
        city = str(row.get('city') or '').strip()
        if hashlib.sha256(f'{name}|{city}'.encode()).hexdigest()[:16] != hospital_id:
            continue
        database_address = str(row.get('address') or '').strip()
        current_address = str(enriched_detail.get('address') or '').strip()
        if database_address and (not current_address or current_address == city or len(database_address) > len(current_address)):
            enriched_detail['address'] = database_address
        if not enriched_detail.get('city') and city:
            enriched_detail['city'] = city
        if database_address and not enriched_detail.get('official_website_url'):
            enriched_detail['official_website_url'] = _safe_http_url(row.get('official_domain'), add_scheme=True)
        if not enriched_detail.get('wechat_appointment') and enriched_detail.get('name'):
            enriched_detail['wechat_appointment'] = f"{enriched_detail['name']}公众号"
        break
    return enriched_detail


@app.get('/v1/hospitals/{hospital_id}')
async def hospital_detail(hospital_id: str, as_of: date = Depends(current_date)):
    database_hospital = await run_in_threadpool(
        lambda: next((row for row in tertiary_rows() if str(row.get('id') or '') == hospital_id), None),
    )
    if database_hospital is not None:
        return {
            'id': hospital_id,
            'name': database_hospital.get('canonical_name'),
            'city': database_hospital.get('city'),
            'district': database_hospital.get('district'),
            'address': database_hospital.get('address'),
            'tier': database_hospital.get('tier'),
            'specialties': [item.get('department') for item in database_hospital.get('specialty_capabilities', []) if item.get('department')],
            'source': {'label': '本地医院数据库', 'date': database_hospital.get('updated_at')},
        }
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
