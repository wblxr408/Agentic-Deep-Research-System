"""
Database layer: PostgreSQL + pgvector and Redis.

Components:
- connection: Connection pool management and initialization
- models: Pydantic models for database entities
- migrate: Database schema migration utilities
"""

from app.db.connection import (
    init_db,
    get_db_pool,
    get_redis,
    close_db,
    Document,
)
from app.db.models import (
    Document as DocumentModel,
    ResearchSession,
    CitationRecord,
)

__all__ = [
    "init_db",
    "get_db_pool",
    "get_redis",
    "close_db",
    "Document",
    "DocumentModel",
    "ResearchSession",
    "CitationRecord",
]
