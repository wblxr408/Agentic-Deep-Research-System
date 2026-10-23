"""Public contracts for read-only research sources."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

ChannelName = Literal["web", "exa", "github", "youtube", "bilibili", "rss", "v2ex",
                      "twitter", "reddit", "xiaohongshu", "facebook", "instagram",
                      "linkedin", "boss", "xueqiu", "xiaoyuzhou"]


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: ChannelName = "web"
    operation: Literal["search", "read"] = "search"
    query: str = Field(min_length=1, max_length=2048)
    limit: int = Field(default=5, ge=1, le=20)
    max_chars: int = Field(default=8000, ge=100, le=20000)

    @field_validator("query")
    @classmethod
    def safe_query(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-") or any(ord(c) < 32 for c in value):
            raise ValueError("query must be nonempty data, not an option or control sequence")
        return value


class SourceItem(BaseModel):
    url: str
    title: str
    content: str
    channel: ChannelName
    backend: str
    collected_at: str
    data_governance:dict=Field(default_factory=dict)


class Attempt(BaseModel):
    channel: ChannelName
    backend: str
    status: str
    result_count: int = 0
    error_category: str | None = None
    duration_ms: int = 0
    call_count: int = 0


class CollectionResult(BaseModel):
    items: list[SourceItem] = Field(default_factory=list)
    attempts: list[Attempt] = Field(default_factory=list)
    status: Literal["success", "empty", "failed", "partial"] = "empty"
    call_count: int = 0


class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    backends: list[str] = Field(default_factory=list, max_length=5)
    timeout_seconds: float = Field(default=20, ge=1, le=90)
    max_attempts: int = Field(default=3, ge=1, le=5)
    feeds: list[str] = Field(default_factory=list, max_length=10)
    transcription_provider: Literal["groq", "openai"] | None = None


class ChannelError(RuntimeError):
    def __init__(self, category: str, *, partial_items: list[dict] | None = None):
        self.category = category
        self.partial_items = partial_items or []
        super().__init__(category)
