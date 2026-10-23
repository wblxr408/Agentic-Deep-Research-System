"""Research information channels."""
from app.channels.models import ChannelConfig, CollectionRequest, CollectionResult
from app.channels.service import ChannelService

__all__ = ["ChannelConfig", "CollectionRequest", "CollectionResult", "ChannelService"]
