from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.governance.mcp import McpPolicyProxy, McpToolRequest


class _FakeConn:
    def __init__(self, row):
        self.row = row

    async def fetchrow(self, *args, **kwargs):
        return self.row

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class _FakePool:
    def __init__(self, row):
        self.row = row

    def acquire(self):
        return _FakeConn(self.row)


def _request(**overrides) -> McpToolRequest:
    payload = {
        "session_id": "session-1",
        "decision_id": None,
        "tool_name": "read_customer",
        "requested_args": {"customer_id": "c-1"},
        "server_id": "crm",
        "approval_id": None,
    }
    payload.update(overrides)
    return McpToolRequest(**payload)


def _registry(**overrides):
    row = {
        "server_id": "crm",
        "trust_status": "trusted",
        "allowed_tools_json": ["read_customer", "write_customer"],
        "read_only_default": True,
        "secret_policy_json": {},
        "fingerprint": "fp-1",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_mcp_policy_blocks_unregistered_server():
    proxy = McpPolicyProxy()

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(None))):
        result = await proxy.invoke(_request())

    assert result.status == "terminal_error"
    assert result.error_category == "untrusted_mcp_server"


@pytest.mark.asyncio
async def test_mcp_policy_blocks_tool_not_allowlisted():
    proxy = McpPolicyProxy()
    row = _registry(allowed_tools_json=["other_tool"])

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request())

    assert result.status == "terminal_error"
    assert result.error_category == "tool_not_allowed"


@pytest.mark.asyncio
async def test_mcp_policy_validates_tool_schema():
    proxy = McpPolicyProxy()
    row = _registry(secret_policy_json={
        "tool_schemas": {
            "read_customer": {
                "type": "object",
                "properties": {"customer_id": {"type": "string"}},
                "required": ["customer_id"],
                "additionalProperties": False,
            }
        }
    })

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request(requested_args={"extra": "bad"}))

    assert result.status == "terminal_error"
    assert result.error_category == "schema_invalid"
    assert "missing required argument" in result.error_message


@pytest.mark.asyncio
async def test_mcp_policy_validates_nested_schema_and_array_items():
    proxy = McpPolicyProxy()
    row = _registry(secret_policy_json={
        "tool_schemas": {
            "write_customer": {
                "type": "object",
                "properties": {
                    "customer": {
                        "type": "object",
                        "required": ["name", "tier"],
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string"},
                            "tier": {"type": "string", "enum": ["standard", "vip"]},
                            "tags": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "required": ["customer"],
                "additionalProperties": False,
            }
        },
    })

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        bad_enum = await proxy.invoke(_request(
            tool_name="write_customer",
            requested_args={"customer": {"name": "Alice", "tier": "gold", "tags": ["a"]}},
        ))
        bad_item = await proxy.invoke(_request(
            tool_name="write_customer",
            requested_args={"customer": {"name": "Alice", "tier": "vip", "tags": ["a", 1]}},
        ))
        bad_extra = await proxy.invoke(_request(
            tool_name="write_customer",
            requested_args={"customer": {"name": "Alice", "tier": "vip", "extra": "bad"}},
        ))

    assert bad_enum.status == "terminal_error"
    assert "customer.tier" in bad_enum.error_message
    assert bad_item.status == "terminal_error"
    assert "customer.tags[1]" in bad_item.error_message
    assert bad_extra.status == "terminal_error"
    assert "customer.extra" in bad_extra.error_message


@pytest.mark.asyncio
async def test_mcp_policy_requires_approval_for_write_tool_without_executor_call():
    executor = AsyncMock()
    proxy = McpPolicyProxy(executor=executor)
    row = _registry(secret_policy_json={"write_tools": ["write_customer"]})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request(tool_name="write_customer", requested_args={"secret": "raw"}))

    assert result.status == "awaiting_approval"
    assert result.approval_request["reason"] == "mcp_write_requires_approval"
    assert result.approval_request["request_payload"]["args"]["secret"] == "[REDACTED]"
    assert result.approval_request["request_payload"]["args_hash"]
    executor.assert_not_called()


@pytest.mark.asyncio
async def test_mcp_policy_approval_id_includes_args_hash_for_idempotency():
    proxy = McpPolicyProxy()
    row = _registry(secret_policy_json={"write_tools": ["write_customer"]})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        first = await proxy.invoke(_request(tool_name="write_customer", requested_args={"name": "Alice", "secret": "raw"}))
        second = await proxy.invoke(_request(tool_name="write_customer", requested_args={"secret": "raw", "name": "Alice"}))
        different = await proxy.invoke(_request(tool_name="write_customer", requested_args={"name": "Bob", "secret": "raw"}))

    assert first.approval_request["approval_id"] == second.approval_request["approval_id"]
    assert first.approval_request["approval_id"] != different.approval_request["approval_id"]
    assert first.approval_request["request_payload"]["args_hash"] == second.approval_request["request_payload"]["args_hash"]
    assert first.approval_request["request_payload"]["args_hash"] != different.approval_request["request_payload"]["args_hash"]


@pytest.mark.asyncio
async def test_mcp_policy_approval_id_uses_raw_args_hash_not_redacted_hash():
    proxy = McpPolicyProxy()
    row = _registry(secret_policy_json={"write_tools": ["write_customer"]})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        first = await proxy.invoke(_request(tool_name="write_customer", requested_args={"name": "Alice", "secret": "raw-a"}))
        second = await proxy.invoke(_request(tool_name="write_customer", requested_args={"name": "Alice", "secret": "raw-b"}))

    assert first.approval_request["request_payload"]["args"] == second.approval_request["request_payload"]["args"]
    assert first.approval_request["request_payload"]["args_hash"] != second.approval_request["request_payload"]["args_hash"]
    assert first.approval_request["approval_id"] != second.approval_request["approval_id"]


@pytest.mark.asyncio
async def test_mcp_policy_redacts_payload_and_hashes_summary():
    async def _executor(request):
        return {
            "customer_id": request.requested_args["customer_id"],
            "token": "secret-token",
            "nested": [{"api_key": "secret-key"}],
            "safe": "ok",
        }

    proxy = McpPolicyProxy(executor=_executor)
    row = _registry(secret_policy_json={"summary_chars": 1000})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request())

    assert result.status == "success"
    assert result.payload["token"] == "[REDACTED]"
    assert result.payload["nested"][0]["api_key"] == "[REDACTED]"
    assert result.redaction_applied is True
    assert result.result_hash
    assert result.server_fingerprint == "fp-1"


@pytest.mark.asyncio
async def test_mcp_policy_validates_output_schema_structured_content():
    async def _executor(request):
        return {
            "content": [{"type": "text", "text": "customer loaded"}],
            "structuredContent": {"customer": {"id": 123, "tier": "vip"}},
        }

    proxy = McpPolicyProxy(executor=_executor)
    row = _registry(secret_policy_json={
        "tool_schemas": {
            "read_customer": {
                "inputSchema": {
                    "type": "object",
                    "properties": {"customer_id": {"type": "string"}},
                    "required": ["customer_id"],
                    "additionalProperties": False,
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "customer": {
                            "type": "object",
                            "required": ["id"],
                            "additionalProperties": False,
                            "properties": {
                                "id": {"type": "string"},
                                "tier": {"type": "string", "enum": ["standard", "vip"]},
                            },
                        }
                    },
                    "required": ["customer"],
                    "additionalProperties": False,
                },
            }
        },
    })

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request())

    assert result.status == "terminal_error"
    assert result.error_category == "output_schema_invalid"
    assert "output customer.id must be string" in result.error_message


@pytest.mark.asyncio
async def test_mcp_result_hash_is_stable_for_equivalent_payload_order():
    async def _first_executor(request):
        return {"b": 2, "a": {"token": "secret-token", "safe": "ok"}}

    async def _second_executor(request):
        return {"a": {"safe": "ok", "token": "secret-token"}, "b": 2}

    row = _registry(secret_policy_json={"summary_chars": 1000})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        first = await McpPolicyProxy(executor=_first_executor).invoke(_request())
        second = await McpPolicyProxy(executor=_second_executor).invoke(_request())

    assert first.payload == second.payload
    assert first.result_hash == second.result_hash


@pytest.mark.asyncio
async def test_mcp_policy_uses_configured_redaction_keys_and_summary_limit():
    async def _executor(request):
        return {"internal_id": "secret", "visible": "x" * 200}

    proxy = McpPolicyProxy(executor=_executor)
    row = _registry(secret_policy_json={"redact_keys": ["internal_id"], "summary_chars": 80})

    with patch("app.governance.mcp.get_db_pool", AsyncMock(return_value=_FakePool(row))):
        result = await proxy.invoke(_request())

    assert result.payload["internal_id"] == "[REDACTED]"
    assert len(result.result_summary) <= 80
