"""
GramCare – API v1 Router (aggregates all endpoint modules)
"""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    appointments,
    auth,
    encounters,
    media,
    messages,
    patients,
    sync,
    teleconsult,
    triage,
    users,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/api/v1")
api_router.include_router(users.router, prefix="/api/v1")
api_router.include_router(patients.router, prefix="/api/v1")
api_router.include_router(appointments.router, prefix="/api/v1")
api_router.include_router(encounters.router, prefix="/api/v1")
api_router.include_router(sync.router, prefix="/api/v1")
api_router.include_router(teleconsult.router, prefix="/api/v1")
api_router.include_router(messages.router, prefix="/api/v1")
api_router.include_router(media.router, prefix="/api/v1")
api_router.include_router(triage.router, prefix="/api/v1")
