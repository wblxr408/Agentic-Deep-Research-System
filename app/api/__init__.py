# API package
from app.api.auth import router as auth_router
from app.api.channels import router as channels_router
from app.api.backup import router as backup_router
from app.api.config import router as config_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.research import router as research_router
from app.api.skills import router as skills_router
from app.api.workspaces import router as workspaces_router
from app.api.personal_connections import router as personal_connections_router

__all__ = ["auth_router", "channels_router", "backup_router", "config_router", "documents_router", "health_router", "research_router", "skills_router", "workspaces_router", "personal_connections_router"]
