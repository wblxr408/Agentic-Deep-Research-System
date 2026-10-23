"""Authenticated source collection and passive channel maintenance."""
import asyncio

from fastapi import APIRouter, Depends, HTTPException

from app.channels import ChannelService
from app.channels.models import ChannelConfig, ChannelError, ChannelName, CollectionRequest
from app.security.auth import Principal, require_principal

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])
principal_dependency = Depends(require_principal)


async def _run(call, *args):
    try:
        return await asyncio.to_thread(call, *args)
    except ChannelError as exc:
        raise HTTPException(503 if exc.category == "state_unavailable" else 422, exc.category) from None
    except (ValueError, KeyError):
        raise HTTPException(422, "invalid_channel_configuration") from None


@router.get("")
async def list_channels(principal: Principal = principal_dependency):
    return {"items": await _run(ChannelService(principal.id).catalog)}


@router.get("/history")
async def channel_history(principal: Principal = principal_dependency):
    return {"items": await _run(ChannelService(principal.id).history)}


@router.put("/{channel}/config")
async def configure_channel(channel: ChannelName, config: ChannelConfig, principal: Principal = principal_dependency):
    return await _run(ChannelService(principal.id).configure, channel, config)


@router.post("/collect")
async def collect_source(request: CollectionRequest, principal: Principal = principal_dependency):
    return await _run(ChannelService(principal.id).collect, request)
