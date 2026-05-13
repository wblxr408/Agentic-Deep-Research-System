"""
Pydantic models for database entities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Knowledge base document model."""
    id: UUID
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ResearchSession(BaseModel):
    """Research session model."""
    id: UUID
    user_query: str
    status: str = "pending"
    research_plan: list[dict] = Field(default_factory=list)
    final_report: str | None = None
    citations: list[dict] = Field(default_factory=list)
    agent_trace: list[dict] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


class CitationRecord(BaseModel):
    """Citation record model."""
    id: UUID
    session_id: UUID
    citation_id: str
    source_url: str | None = None
    source_title: str | None = None
    source_type: str = "web"
    extracted_evidence: str | None = None
    relevance_score: float = 0.0
    access_timestamp: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
