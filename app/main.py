"""
FastAPI application entry point.

Initializes the app, middleware, routes, and startup/shutdown handlers.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import get_settings
from app.api import research_router, health_router, config_router, documents_router, skills_router
from app.db.connection import init_db, close_db
from app.skills import get_skill_registry

# ==============================================================
# Structured Logging Setup
# ==============================================================

def setup_logging():
    """Configure structured logging with structlog."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer()
                if sys.stderr.isatty() is False
                else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


setup_logging()
logger = structlog.get_logger(__name__)

# ==============================================================
# Lifespan Management
# ==============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown handlers."""
    settings = get_settings()
    logger.info("Starting DeepIntel API", version="1.0.0")

    # Startup
    try:
        await init_db()
        await get_skill_registry().load()
        logger.info("Database initialized")
    except Exception as e:
        logger.error("Database initialization failed", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Shutting down DeepIntel API")
    await close_db()


# ==============================================================
# App Factory
# ==============================================================

def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Agentic Deep Research System",
        description=(
            "An autonomous AI research platform powered by LangGraph. "
            "Supports multi-agent workflows, browser automation, RAG, "
            "and citation-grounded report generation."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # GZip compression
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Register routes
    app.include_router(health_router)
    app.include_router(research_router)
    app.include_router(config_router)
    app.include_router(documents_router)
    app.include_router(skills_router)

    # Root endpoint
    @app.get("/")
    async def root():
        return {
            "name": "Agentic Deep Research System",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/v1/health",
            "ready": "/api/v1/ready",
        }

    return app


# Create app instance
app = create_app()


# ==============================================================
# Development Server Entry Point
# ==============================================================

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.api.host,
        port=settings.api.port,
        reload=settings.api.reload,
        log_level=settings.api.log_level.lower(),
    )
