"""Enterprise RAG Platform — FastAPI Application Factory.

Initializes all middleware, exception handlers, routers, and
dependency lifecycle (DB, Redis, etc.) via FastAPI lifespan.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.router import router as api_v1_router
from app.cache.redis import redis_manager
from app.core.config import settings
from app.core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
    app_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import get_logger, setup_logging
from app.storage.exceptions import (
    StorageError,
    StorageFileNotFound,
    StoragePermissionDenied,
    StorageQuotaExceeded,
    StorageUnavailable,
)
from app.db.session import async_session_factory, init_db, shutdown_db
from app.middleware.cors import setup_cors
from app.middleware.logging import setup_request_logging
from app.middleware.rate_limit import setup_rate_limiting
from app.middleware.security import setup_security_headers
from app.storage.factory import create_storage_provider, shutdown_storage_provider
from app.embeddings.providers.factory import shutdown_embedding_provider
from app.vector_stores.factory import close_vector_store
from app.embeddings.services.indexing_service import shutdown_indexing_service

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — initialize and clean up resources."""
    # Startup
    setup_logging()
    logger.info(
        "Starting application",
        environment=settings.ENVIRONMENT.value,
        project=settings.PROJECT_NAME,
    )

    # Initialize database
    try:
        await init_db()
        logger.info("Database connection established")
    except Exception as e:
        logger.warning("Database initialization failed (non-fatal — running in degraded mode)", exc_info=e)

    # Initialize Redis
    try:
        await redis_manager.initialize()
        logger.info("Redis connection established")
    except Exception as e:
        logger.warning("Redis initialization failed (non-fatal)", exc_info=e)

    # Initialize storage provider
    try:
        await create_storage_provider()
        logger.info("Storage provider initialized", provider=settings.STORAGE_PROVIDER)
    except Exception as e:
        logger.error("Storage provider initialization failed", exc_info=e)
        raise

    # Initialize embedding provider
    try:
        from app.embeddings.providers.factory import create_embedding_provider
        embedding_provider = await create_embedding_provider()
        logger.info("Embedding provider initialized", provider=settings.EMBEDDING_PROVIDER)
    except Exception as e:
        logger.error("Embedding provider initialization failed", exc_info=e)
        raise

    # Initialize vector store
    try:
        from app.vector_stores.factory import create_vector_store
        vector_store = await create_vector_store()
        from app.vector_stores.factory import get_vector_store as _get_vs
        async for vs in _get_vs():
            vector_store = vs
            break
    except Exception as e:
        logger.warning("Vector store initialization failed (non-fatal)", exc_info=e)

    # Initialize IndexingService as application-scoped singleton
    try:
        from app.vector_stores.collection_manager import CollectionManager
        from app.vector_stores.factory import get_collection_manager as _get_cm
        collection_manager = None
        async for cm in _get_cm():
            collection_manager = cm
            break
        from app.embeddings.services.indexing_service import init_indexing_service
        await init_indexing_service(
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            collection_manager=collection_manager,
        )
        logger.info("IndexingService initialized as application singleton")
    except Exception as e:
        logger.warning("IndexingService initialization failed (non-fatal)", exc_info=e)

    # Store session factory for health checks
    async def get_health_db() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_factory() as session:
            yield session

    app.state.db_session_factory = get_health_db

    yield

    # Shutdown — resource ordering: services → connections
    logger.info("Shutting down application")
    await shutdown_indexing_service()
    await shutdown_embedding_provider()
    await close_vector_store()
    await shutdown_storage_provider()
    await shutdown_db()
    await redis_manager.close()
    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.1.0",
        description="""
        Enterprise Agentic RAG Platform.

        Production-grade retrieval-augmented generation system with
        multi-agent orchestration, knowledge graphs, and hybrid search.
        """,
        docs_url=f"{settings.API_V1_PREFIX}/docs" if settings.ENVIRONMENT != "production" else None,
        redoc_url=f"{settings.API_V1_PREFIX}/redoc" if settings.ENVIRONMENT != "production" else None,
        openapi_url=f"{settings.API_V1_PREFIX}/openapi.json" if settings.ENVIRONMENT != "production" else None,
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
        swagger_ui_parameters={
            "deepLinking": True,
            "defaultModelsExpandDepth": 2,
            "defaultModelExpandDepth": 2,
            "docExpansion": "list",
            "syntaxHighlight": True,
        },
    )

    # ── Middleware (order matters: first added = last executed) ──
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    setup_cors(app)
    setup_security_headers(app)
    setup_request_logging(app)
    setup_rate_limiting(app)

    # ── Exception Handlers ────────────────────
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    from fastapi.exceptions import HTTPException, RequestValidationError

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # ── Storage Exception Handlers ────────────
    @app.exception_handler(StorageFileNotFound)
    async def storage_not_found_handler(
        request: Request, exc: StorageFileNotFound
    ) -> ORJSONResponse:
        from fastapi import status
        return ORJSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(StoragePermissionDenied)
    async def storage_permission_handler(
        request: Request, exc: StoragePermissionDenied
    ) -> ORJSONResponse:
        from fastapi import status
        return ORJSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(StorageQuotaExceeded)
    async def storage_quota_handler(
        request: Request, exc: StorageQuotaExceeded
    ) -> ORJSONResponse:
        from fastapi import status
        return ORJSONResponse(
            status_code=status.HTTP_507_INSUFFICIENT_STORAGE,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(StorageUnavailable)
    async def storage_unavailable_handler(
        request: Request, exc: StorageUnavailable
    ) -> ORJSONResponse:
        from fastapi import status
        return ORJSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    @app.exception_handler(StorageError)
    async def storage_error_handler(
        request: Request, exc: StorageError
    ) -> ORJSONResponse:
        from fastapi import status
        return ORJSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                }
            },
        )

    # ── Routers ───────────────────────────────
    app.include_router(api_v1_router)

    # ── Root endpoint ─────────────────────────
    @app.get("/", tags=["root"])
    async def root() -> dict[str, Any]:
        """Root endpoint with API information."""
        return {
            "name": settings.PROJECT_NAME,
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT.value,
            "docs": f"{settings.API_V1_PREFIX}/docs",
            "health": f"{settings.API_V1_PREFIX}/health",
        }

    logger.info(
        "Application created",
        docs_url=app.docs_url,
        redoc_url=app.redoc_url,
    )

    return app


app = create_app()
"""Application instance for ASGI servers (uvicorn, gunicorn)."""
