from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.db.connection import get_db_pool

SECRET_KEYS = {"api_key", "token", "secret", "password", "authorization"}


@dataclass
class McpToolRequest:
    session_id: str
    decision_id: str | None
    tool_name: str
    requested_args: dict[str, Any]
    server_id: str
    approval_id: str | None = None


@dataclass
class McpToolResult:
    status: str
    result_summary: str | None = None
    result_hash: str | None = None
    server_fingerprint: str | None = None
    redaction_applied: bool = False
    error_category: str | None = None
    error_message: str | None = None
    approval_request: dict[str, Any] | None = None
    payload: Any | None = None


class McpPolicyProxy:
    """Governed MCP entrypoint: allowlist, trust, readonly-default, redaction."""

    def __init__(self, executor: Callable[[McpToolRequest], Awaitable[Any]] | None = None):
        self.executor = executor

    async def invoke(self, request: McpToolRequest) -> McpToolResult:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            registry = await conn.fetchrow(
                """
                SELECT server_id, trust_status, allowed_tools_json, read_only_default,
                       secret_policy_json, fingerprint
                FROM mcp_server_registry
                WHERE server_id = $1
                """,
                request.server_id,
            )
        if not registry:
            return McpToolResult(
                status="terminal_error",
                error_category="untrusted_mcp_server",
                error_message=f"unregistered server: {request.server_id}",
            )
        if registry["trust_status"] != "trusted":
            return McpToolResult(
                status="terminal_error",
                error_category="untrusted_mcp_server",
                error_message=f"untrusted server: {request.server_id}",
                server_fingerprint=registry["fingerprint"],
            )

        allowed_tools = set(registry["allowed_tools_json"] or [])
        if request.tool_name not in allowed_tools:
            return McpToolResult(
                status="terminal_error",
                error_category="tool_not_allowed",
                error_message=f"tool not allowlisted: {request.tool_name}",
                server_fingerprint=registry["fingerprint"],
            )

        read_only_default = bool(registry["read_only_default"])
        if not read_only_default and not request.approval_id:
            approval_request = {
                "approval_id": f"ap-{hashlib.sha256(f'{request.session_id}:{request.server_id}:{request.tool_name}'.encode()).hexdigest()[:12]}",
                "node_id": None,
                "tool_name": request.tool_name,
                "risk_level": "high",
                "reason": "mcp_write_requires_approval",
                "request_payload": {
                    "server_id": request.server_id,
                    "tool_name": request.tool_name,
                    "args": self._redact(request.requested_args)[0],
                },
                "status": "pending",
            }
            return McpToolResult(
                status="awaiting_approval",
                approval_request=approval_request,
                server_fingerprint=registry["fingerprint"],
            )

        if self.executor is None:
            return McpToolResult(
                status="terminal_error",
                error_category="unsupported_input",
                error_message="no MCP executor configured",
                server_fingerprint=registry["fingerprint"],
            )

        payload = await self.executor(request)
        redacted, redaction_applied = self._redact(payload)
        summary = str(redacted)[:500]
        return McpToolResult(
            status="success",
            result_summary=summary,
            result_hash=hashlib.sha256(summary.encode("utf-8")).hexdigest(),
            server_fingerprint=registry["fingerprint"],
            redaction_applied=redaction_applied,
            payload=redacted,
        )

    def _redact(self, value: Any) -> tuple[Any, bool]:
        if isinstance(value, dict):
            changed = False
            output: dict[str, Any] = {}
            for key, item in value.items():
                if str(key).lower() in SECRET_KEYS:
                    output[key] = "[REDACTED]"
                    changed = True
                else:
                    redacted, child_changed = self._redact(item)
                    output[key] = redacted
                    changed = changed or child_changed
            return output, changed
        if isinstance(value, list):
            changed = False
            output = []
            for item in value:
                redacted, child_changed = self._redact(item)
                output.append(redacted)
                changed = changed or child_changed
            return output, changed
        return value, False
