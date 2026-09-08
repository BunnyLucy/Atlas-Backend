import time
import uuid

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import get_settings
from .db import engine
from .errors import AtlasError
from .routers import auth, memberships, notifications, workflow, worlds

settings = get_settings()
log = structlog.get_logger()
app = FastAPI(title="Atlas API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(settings.web_origin).rstrip("/")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    log.info("request", request_id=request_id, method=request.method, path=request.url.path, status=response.status_code, duration_ms=round((time.perf_counter() - started) * 1000, 2))
    return response


@app.exception_handler(AtlasError)
async def atlas_error_handler(request: Request, error: AtlasError) -> JSONResponse:
    return JSONResponse(status_code=error.status_code, content={"error": {"code": error.code, "message": error.message, "details": error.details}, "requestID": request.headers.get("x-request-id")})


@app.get("/health")
async def health() -> dict:
    async with engine.connect() as connection:
        await connection.execute(text("select 1"))
    return {"ok": True, "service": "atlas-python-api"}


app.include_router(auth.router, prefix="/api/v1")
app.include_router(worlds.router, prefix="/api/v1")
app.include_router(memberships.router, prefix="/api/v1")
app.include_router(workflow.router, prefix="/api/v1")
app.include_router(notifications.router, prefix="/api/v1")
