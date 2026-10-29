"""
app/main.py
-----------
FastAPI application entry point for Agentic AI Data Analyst.
Includes lifespan connection management, CORS, request size limiting middleware,
custom error formatting, and Swagger/OpenAPI documentation.
"""

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from app.config import settings
from app.database import readonly_engine, admin_engine, check_database_health
from app.security.middleware import RateLimitMiddleware, APIKeyAuthMiddleware
from app.api.routes import router as api_router

# Configure root logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("agentic_ai.main")


# ------------------------------------------------------------------------------
# 1. Lifespan Management (Startup & Graceful Shutdown)
# ------------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan context manager.
    Initializes database pools on startup and disposes them cleanly on shutdown.
    """
    logger.info(f"Starting {settings.APP_TITLE} (v{settings.APP_VERSION})...")
    health = check_database_health()
    if health["connected"]:
        logger.info(f"Database connection verified successfully. Dialect: {health['dialect']}, Latency: {health['latency_ms']}ms")
    else:
        logger.warning(f"Database is currently unavailable: {health.get('error')}")

    yield

    logger.info("Shutting down application and disposing connection pools...")
    readonly_engine.dispose()
    admin_engine.dispose()
    logger.info("Connection pools disposed successfully.")


# ------------------------------------------------------------------------------
# 2. Request Size Limiting Middleware
# ------------------------------------------------------------------------------
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Protects the API from memory exhaustion / Denial of Service by rejecting
    HTTP requests exceeding the configured byte limit (settings.MAX_REQUEST_BODY_BYTES).
    """
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                length = int(content_length)
                if length > settings.MAX_REQUEST_BODY_BYTES:
                    status_code = status.HTTP_413_CONTENT_TOO_LARGE
                    return JSONResponse(
                        status_code=status_code,
                        content={
                            "error": "Request payload too large",
                            "details": f"Body size of {length} bytes exceeds maximum limit of {settings.MAX_REQUEST_BODY_BYTES} bytes.",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    )
            except ValueError:
                pass
        return await call_next(request)


# ------------------------------------------------------------------------------
# 3. Application Factory
# ------------------------------------------------------------------------------
def create_app() -> FastAPI:
    """Builds and configures the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_TITLE,
        version=settings.APP_VERSION,
        description=(
            "Production-ready backend API for the Agentic AI Data Analyst. "
            "Exposes controlled, read-only analytics endpoints, dynamic schema inspection, "
            "and health monitoring with strict AST-level security boundaries."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan
    )

    # CORS Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Security Middlewares
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(APIKeyAuthMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)

    # Mount API routers
    app.include_router(api_router)

    # Root welcome endpoint
    @app.get("/", tags=["General"])
    def root():
        return {
            "name": settings.APP_TITLE,
            "version": settings.APP_VERSION,
            "status": "operational",
            "documentation": "/docs",
            "schema_endpoint": "/schema",
            "health_endpoint": "/health"
        }

    return app


app = create_app()
