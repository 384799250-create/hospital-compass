import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.matcher import match
from app.schemas import MatchRequest

logger = logging.getLogger(__name__)
app = FastAPI()


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


@app.post('/v1/matches')
async def matches(request: MatchRequest):
    return match(request.query, request.city, request.priority)
