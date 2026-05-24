# API package
from app.api.research import router as research_router
from app.api.health import router as health_router
from app.api.config import router as config_router
from app.api.documents import router as documents_router

__all__ = ["research_router", "health_router", "config_router", "documents_router"]
