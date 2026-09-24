"""
GramCare – FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

import socketio
import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.db.session import init_db
from app.realtime.socketio_app import sio

# ── Logging setup ─────────────────────────────────────────────────────────────
structlog.configure(
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.DEBUG if settings.DEBUG else logging.INFO
    )
)
logger = structlog.get_logger()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("GramCare API starting up…")
    # Schema is normally owned by Alembic (`alembic upgrade head`).
    # AUTO_CREATE_TABLES=true is an opt-in convenience for a fresh local
    # Postgres with no migrations run yet.
    if settings.AUTO_CREATE_TABLES:
        await init_db()
        await _create_sync_sequence()
    logger.info("GramCare API ready.")
    yield
    logger.info("GramCare API shutting down.")


async def _create_sync_sequence():
    """Create the PostgreSQL sequence used for sync versioning."""
    from sqlalchemy import text
    from app.db.session import engine
    async with engine.begin() as conn:
        await conn.execute(
            text("CREATE SEQUENCE IF NOT EXISTS sync_version_seq START 1 INCREMENT 1")
        )


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="GramCare API",
    description=(
        "GramCare – Offline-first, low-bandwidth telehealth platform for rural India. "
        "Backend REST API with sync, teleconsultation, triage, and media services."
    ),
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)


# ── Request logging middleware ─────────────────────────────────────────────────

@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(
        "request",
        method=request.method,
        url=str(request.url),
        client=request.client.host if request.client else "unknown",
    )
    response = await call_next(request)
    logger.info("response", status_code=response.status_code)
    return response


# ── Global exception handler ──────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("unhandled_error", error=str(exc), url=str(request.url))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again."},
    )


# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(api_router)


@app.get("/", tags=["Health"])
async def root():
    return {
        "service": "GramCare API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    from datetime import datetime, timezone
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": settings.APP_ENV,
    }


# ── Combined ASGI app: REST (FastAPI) + WebRTC signaling/chat (Socket.IO) ────
# Run this with uvicorn, not `app`, so /socket.io/* is served alongside the
# REST API on the same port: `uvicorn app.main:socket_app`.
socket_app = socketio.ASGIApp(sio, other_asgi_app=app, socketio_path="/socket.io")
