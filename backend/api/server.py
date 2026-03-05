"""FastAPI application with CORS middleware and health check."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers.sessions import router as sessions_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="InterviewOS API",
        description="REST API for InterviewOS session management",
        version="0.1.0",
    )

    # CORS middleware — allow all origins in development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(sessions_router)

    # Health check
    @app.get("/health")
    def health_check() -> dict:
        """Health check endpoint."""
        return {"status": "ok"}

    return app


app = create_app()
