"""
Health check API endpoints.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: str
    version: str
    python_version: str


class ReadinessResponse(BaseModel):
    status: str
    database: str
    redis: str
    timestamp: str


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version="1.0.0",
        python_version=sys.version,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check():
    """
    Readiness check: verify all dependencies are available.

    Checks:
    - PostgreSQL connection
    - Redis connection
    """
    db_status = "unknown"
    redis_status = "unknown"

    # Check database
    try:
        from app.db.connection import get_db_pool
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_status = "connected"
    except Exception as e:
        logger.warning(f"Database readiness check failed: {e}")
        db_status = f"error: {e}"

    # Check Redis
    try:
        from app.db.connection import get_redis
        redis = await get_redis()
        await redis.ping()
        redis_status = "connected"
    except Exception as e:
        logger.warning(f"Redis readiness check failed: {e}")
        redis_status = f"error: {e}"

    overall_status = "ready" if (db_status == "connected" and redis_status == "connected") else "degraded"

    return ReadinessResponse(
        status=overall_status,
        database=db_status,
        redis=redis_status,
        timestamp=datetime.utcnow().isoformat(),
    )
