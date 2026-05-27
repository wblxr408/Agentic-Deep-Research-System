"""
LLM Client Factory - Creates LLM clients with runtime configuration.

Priority: Runtime config > DB config > Environment variables
"""

from __future__ import annotations

import logging
from typing import Any

from openai import OpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

MODEL_PRICING_USD_PER_1K: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.005, 0.015),
}


def get_llm_client_config() -> dict[str, Any]:
    """
    Get LLM client configuration with priority:
    1. Runtime config (set via API)
    2. Database config
    3. Environment variables

    Returns:
        Dict with provider, model, api_key, api_base, temperature, max_tokens
    """
    from app.api.config import get_runtime_llm_config

    # Check runtime config first
    runtime_config = get_runtime_llm_config()
    if runtime_config:
        return {
            "provider": runtime_config.provider,
            "model": runtime_config.model,
            "api_key": runtime_config.api_key,
            "api_base": runtime_config.api_base,
            "temperature": runtime_config.temperature,
            "max_tokens": runtime_config.max_tokens,
        }

    # Fallback to environment variables
    settings = get_settings()
    return {
        "provider": settings.llm.provider,
        "model": settings.llm.model,
        "api_key": settings.llm.api_key,
        "api_base": settings.llm.api_base,
        "temperature": settings.llm.temperature,
        "max_tokens": settings.llm.max_tokens,
    }


def create_llm_client(
    api_key: str | None = None,
    api_base: str | None = None,
) -> OpenAI:
    """
    Create an OpenAI-compatible LLM client.

    Uses runtime config if available, otherwise falls back to env vars.

    Args:
        api_key: Override API key (optional)
        api_base: Override API base URL (optional)

    Returns:
        OpenAI client instance
    """
    config = get_llm_client_config()

    final_api_key = api_key or config.get("api_key", "")
    final_api_base = api_base or config.get("api_base")

    if not final_api_key:
        settings = get_settings()
        final_api_key = settings.llm.api_key

    client_kwargs: dict[str, Any] = {
        "api_key": final_api_key,
    }

    if final_api_base:
        client_kwargs["base_url"] = final_api_base

    return OpenAI(**client_kwargs)


def get_llm_model() -> str:
    """Get the current LLM model name."""
    config = get_llm_client_config()
    return config.get("model", "qwen-plus")


def get_llm_temperature() -> float:
    """Get the current LLM temperature."""
    config = get_llm_client_config()
    return config.get("temperature", 0.7)


def get_llm_max_tokens() -> int:
    """Get the current LLM max tokens."""
    config = get_llm_client_config()
    return config.get("max_tokens", 8192)


def estimate_text_tokens(text: str | None) -> int:
    """Approximate token count using a conservative chars-per-token heuristic."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def estimate_messages_tokens(messages: list[dict[str, Any]] | None) -> int:
    """Approximate token usage for OpenAI-style chat messages."""
    if not messages:
        return 0
    total_chars = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        total_chars += len(str(message.get("role", "")))
        content = message.get("content", "")
        if isinstance(content, list):
            total_chars += sum(len(str(part)) for part in content)
        else:
            total_chars += len(str(content))
    return estimate_text_tokens("x" * total_chars)


def estimate_cost_usd(
    model: str | None,
    *,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate request cost for models with known pricing."""
    if not model:
        return 0.0
    pricing = MODEL_PRICING_USD_PER_1K.get(model)
    if not pricing:
        return 0.0
    prompt_price, completion_price = pricing
    return round((prompt_tokens / 1000.0) * prompt_price + (completion_tokens / 1000.0) * completion_price, 6)


def collect_usage_metrics(
    *,
    response: Any | None = None,
    model: str | None = None,
    messages: list[dict[str, Any]] | None = None,
    completion_text: str | None = None,
) -> dict[str, Any]:
    """
    Normalize provider usage into a stable structure.

    If the provider does not return usage, fall back to a simple token estimate.
    """
    usage_obj = getattr(response, "usage", None) if response is not None else None
    if usage_obj is None and isinstance(response, dict):
        usage_obj = response.get("usage")

    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    estimated = False

    if usage_obj is not None:
        if isinstance(usage_obj, dict):
            prompt_tokens = usage_obj.get("prompt_tokens")
            completion_tokens = usage_obj.get("completion_tokens")
            total_tokens = usage_obj.get("total_tokens")
        else:
            prompt_tokens = getattr(usage_obj, "prompt_tokens", None)
            completion_tokens = getattr(usage_obj, "completion_tokens", None)
            total_tokens = getattr(usage_obj, "total_tokens", None)

    if prompt_tokens is None:
        prompt_tokens = estimate_messages_tokens(messages)
        estimated = True
    if completion_tokens is None:
        completion_tokens = estimate_text_tokens(completion_text)
        estimated = True
    if total_tokens is None:
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
        estimated = True

    cost_usd = estimate_cost_usd(
        model,
        prompt_tokens=int(prompt_tokens or 0),
        completion_tokens=int(completion_tokens or 0),
    )
    if cost_usd == 0.0 and total_tokens:
        estimated = True

    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
        "cost_usd": float(cost_usd),
        "estimated": estimated,
        "model": model,
    }


class LLMClientWrapper:
    """
    Wrapper that provides a lazily-initialized LLM client.

    Usage:
        client_wrapper = LLMClientWrapper()
        response = client_wrapper.client.chat.completions.create(...)
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
    ):
        self._api_key = api_key
        self._api_base = api_base
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        """Get or create the LLM client."""
        if self._client is None:
            self._client = create_llm_client(
                api_key=self._api_key,
                api_base=self._api_base,
            )
        return self._client

    @property
    def model(self) -> str:
        """Get the current model name."""
        return get_llm_model()

    @property
    def temperature(self) -> float:
        """Get the current temperature."""
        return get_llm_temperature()

    @property
    def max_tokens(self) -> int:
        """Get the current max tokens."""
        return get_llm_max_tokens()

    def reset(self) -> None:
        """Reset the client to pick up new config."""
        self._client = None
