"""
LLM Configuration API - Frontend configurable LLM settings.

Allows runtime configuration of LLM provider, model, API key, etc.
Configuration is stored in database and overrides environment variables.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import get_settings, Settings, LLMSettings
from app.db.connection import get_db_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/config", tags=["config"])


# ==============================================================
# Request/Response Models
# ==============================================================

class LLMConfigRequest(BaseModel):
    """Request body for updating LLM configuration."""
    provider: Literal["qwen", "deepseek", "openai"] = Field(
        ...,
        description="LLM provider: qwen, deepseek, or openai"
    )
    model: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Model name, e.g., qwen-plus, deepseek-chat, gpt-4o"
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="API key for the provider"
    )
    api_base: str | None = Field(
        default=None,
        description="Custom API base URL (optional, for proxies/ollama)"
    )
    temperature: float = Field(
        default=0.7,
        ge=0.0,
        le=2.0,
        description="Generation temperature"
    )
    max_tokens: int = Field(
        default=8192,
        ge=256,
        le=32768,
        description="Max tokens for generation"
    )
    # Fallback settings
    fallback_provider: Literal["qwen", "deepseek", "openai"] | None = Field(
        default=None,
        description="Fallback provider when primary fails"
    )
    fallback_model: str | None = Field(
        default=None,
        description="Fallback model name"
    )
    fallback_api_key: str | None = Field(
        default=None,
        description="Fallback API key"
    )


class LLMConfigResponse(BaseModel):
    """Response for LLM configuration."""
    provider: str
    model: str
    api_key_masked: str  # Masked for security
    api_base: str | None
    temperature: float
    max_tokens: int
    fallback_provider: str | None
    fallback_model: str | None
    has_fallback_api_key: bool
    updated_at: str | None


class LLMConfigStatus(BaseModel):
    """Status response for LLM configuration."""
    is_configured: bool
    provider: str | None
    model: str | None
    has_api_key: bool
    last_updated: str | None


# ==============================================================
# Helper Functions
# ==============================================================

def mask_api_key(api_key: str) -> str:
    """Mask API key for display, showing only first 8 and last 4 chars."""
    if len(api_key) <= 12:
        return "*" * len(api_key)
    return f"{api_key[:8]}...{api_key[-4:]}"


async def get_llm_config_from_db() -> dict[str, Any] | None:
    """Get LLM configuration from database."""
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT config_data, updated_at
                FROM system_config
                WHERE config_key = 'llm'
                """
            )
            if row:
                return {
                    "data": row["config_data"],
                    "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
                }
    except Exception as e:
        logger.warning(f"Failed to get LLM config from DB: {e}")
    return None


async def save_llm_config_to_db(config: LLMConfigRequest) -> None:
    """Save LLM configuration to database."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO system_config (config_key, config_data, updated_at)
            VALUES ('llm', $1::jsonb, $2)
            ON CONFLICT (config_key) DO UPDATE SET
                config_data = $1::jsonb,
                updated_at = $2
            """,
            config.model_dump(),
            datetime.utcnow(),
        )


# ==============================================================
# Global Runtime Config Cache
# ==============================================================

_runtime_llm_config: LLMConfigRequest | None = None


def get_runtime_llm_config() -> LLMConfigRequest | None:
    """Get the runtime LLM configuration."""
    return _runtime_llm_config


def set_runtime_llm_config(config: LLMConfigRequest) -> None:
    """Set the runtime LLM configuration."""
    global _runtime_llm_config
    _runtime_llm_config = config
    logger.info(f"Runtime LLM config updated: provider={config.provider}, model={config.model}")


# ==============================================================
# API Endpoints
# ==============================================================

@router.get("/llm", response_model=LLMConfigResponse)
async def get_llm_config():
    """
    Get current LLM configuration.

    Returns masked API key for security.
    Priority: Runtime config > DB config > Environment variables
    """
    # Check runtime config first
    if _runtime_llm_config:
        config = _runtime_llm_config
        return LLMConfigResponse(
            provider=config.provider,
            model=config.model,
            api_key_masked=mask_api_key(config.api_key),
            api_base=config.api_base,
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            fallback_provider=config.fallback_provider,
            fallback_model=config.fallback_model,
            has_fallback_api_key=bool(config.fallback_api_key),
            updated_at=None,
        )

    # Check DB config
    db_config = await get_llm_config_from_db()
    if db_config:
        data = db_config["data"]
        return LLMConfigResponse(
            provider=data.get("provider", "qwen"),
            model=data.get("model", "qwen-plus"),
            api_key_masked=mask_api_key(data.get("api_key", "")),
            api_base=data.get("api_base"),
            temperature=data.get("temperature", 0.7),
            max_tokens=data.get("max_tokens", 8192),
            fallback_provider=data.get("fallback_provider"),
            fallback_model=data.get("fallback_model"),
            has_fallback_api_key=bool(data.get("fallback_api_key")),
            updated_at=db_config.get("updated_at"),
        )

    # Fallback to environment variables
    settings = get_settings()
    return LLMConfigResponse(
        provider=settings.llm.provider,
        model=settings.llm.model,
        api_key_masked=mask_api_key(settings.llm.api_key) if settings.llm.api_key else "",
        api_base=settings.llm.api_base,
        temperature=settings.llm.temperature,
        max_tokens=settings.llm.max_tokens,
        fallback_provider=settings.llm.fallback_provider,
        fallback_model=settings.llm.fallback_model,
        has_fallback_api_key=bool(settings.llm.fallback_api_key),
        updated_at=None,
    )


@router.post("/llm", response_model=LLMConfigResponse)
async def update_llm_config(config: LLMConfigRequest):
    """
    Update LLM configuration.

    Configuration is saved to database and set as runtime config.
    This affects all subsequent LLM calls.
    """
    logger.info(f"Updating LLM config: provider={config.provider}, model={config.model}")

    # Validate provider-specific model names
    provider_models = {
        "qwen": ["qwen-plus", "qwen-turbo", "qwen-max", "qwen-long", "qwen2.5-72b-instruct"],
        "deepseek": ["deepseek-chat", "deepseek-coder", "deepseek-reasoner"],
        "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo", "o1", "o1-mini"],
    }

    if config.provider in provider_models:
        valid_models = provider_models[config.provider]
        if config.model not in valid_models:
            logger.warning(
                f"Model '{config.model}' may not be valid for provider '{config.provider}'. "
                f"Valid models: {valid_models}"
            )

    # Save to database
    await save_llm_config_to_db(config)

    # Set runtime config
    set_runtime_llm_config(config)

    return LLMConfigResponse(
        provider=config.provider,
        model=config.model,
        api_key_masked=mask_api_key(config.api_key),
        api_base=config.api_base,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        fallback_provider=config.fallback_provider,
        fallback_model=config.fallback_model,
        has_fallback_api_key=bool(config.fallback_api_key),
        updated_at=datetime.utcnow().isoformat(),
    )


@router.get("/llm/status", response_model=LLMConfigStatus)
async def get_llm_status():
    """
    Get LLM configuration status.

    Returns whether LLM is configured and has valid API key.
    """
    # Check if we have a valid config
    has_config = False
    provider = None
    model = None
    has_key = False
    last_updated = None

    if _runtime_llm_config:
        has_config = True
        provider = _runtime_llm_config.provider
        model = _runtime_llm_config.model
        has_key = bool(_runtime_llm_config.api_key)
    else:
        db_config = await get_llm_config_from_db()
        if db_config:
            has_config = True
            data = db_config["data"]
            provider = data.get("provider")
            model = data.get("model")
            has_key = bool(data.get("api_key"))
            last_updated = db_config.get("updated_at")
        else:
            settings = get_settings()
            has_config = bool(settings.llm.api_key)
            provider = settings.llm.provider
            model = settings.llm.model
            has_key = bool(settings.llm.api_key)

    return LLMConfigStatus(
        is_configured=has_config and has_key,
        provider=provider,
        model=model,
        has_api_key=has_key,
        last_updated=last_updated,
    )


@router.get("/llm/providers")
async def get_available_providers():
    """
    Get available LLM providers and their models.

    Returns a list of supported providers and their recommended models.
    """
    return {
        "providers": [
            {
                "id": "qwen",
                "name": "通义千问 (Qwen)",
                "description": "阿里云大模型，中文能力强，工具调用优秀",
                "models": [
                    {"id": "qwen-plus", "name": "Qwen Plus", "description": "推荐，性价比高"},
                    {"id": "qwen-turbo", "name": "Qwen Turbo", "description": "速度快，成本低"},
                    {"id": "qwen-max", "name": "Qwen Max", "description": "最强能力"},
                    {"id": "qwen-long", "name": "Qwen Long", "description": "超长上下文"},
                ],
                "api_base_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "recommended": True,
            },
            {
                "id": "deepseek",
                "name": "DeepSeek",
                "description": "国产大模型，性价比极高",
                "models": [
                    {"id": "deepseek-chat", "name": "DeepSeek Chat", "description": "通用对话模型"},
                    {"id": "deepseek-coder", "name": "DeepSeek Coder", "description": "代码专用"},
                    {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner", "description": "深度推理"},
                ],
                "api_base_default": "https://api.deepseek.com/v1",
                "recommended": True,
            },
            {
                "id": "openai",
                "name": "OpenAI",
                "description": "GPT 系列，国际领先",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o", "description": "最新旗舰"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "description": "轻量快速"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "description": "经典强力"},
                    {"id": "o1", "name": "o1", "description": "深度推理"},
                    {"id": "o1-mini", "name": "o1 Mini", "description": "轻量推理"},
                ],
                "api_base_default": "https://api.openai.com/v1",
                "recommended": False,
            },
        ],
        "default": {
            "provider": "qwen",
            "model": "qwen-plus",
        },
    }


@router.delete("/llm")
async def reset_llm_config():
    """
    Reset LLM configuration to environment defaults.

    Removes runtime and database configuration.
    """
    global _runtime_llm_config
    _runtime_llm_config = None

    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM system_config WHERE config_key = 'llm'
                """
            )
    except Exception as e:
        logger.warning(f"Failed to delete LLM config from DB: {e}")

    return {"message": "LLM configuration reset to environment defaults"}
