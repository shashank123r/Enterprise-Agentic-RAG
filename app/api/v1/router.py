"""API v1 main router — aggregates all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import auth, documents, health, users

router = APIRouter(prefix="/api/v1")

# Health checks (unauthenticated)
router.include_router(health.router, tags=["health"])

# Authentication (unauthenticated)
router.include_router(auth.router, prefix="/auth", tags=["authentication"])

# User management (authenticated)
router.include_router(users.router, prefix="/users", tags=["users"])

# Document ingestion (authenticated)
router.include_router(documents.router, prefix="/documents", tags=["documents"])

# Indexing (authenticated)
from app.api.v1.endpoints import indexing
router.include_router(indexing.router, tags=["indexing"])

# Retrieval (authenticated)
from app.api.v1.endpoints import retrieval
router.include_router(retrieval.router, tags=["retrieval"])

# RAG Chat (authenticated)
from app.api.v1.endpoints import rag
router.include_router(rag.router, tags=["rag"])

# RAG Evaluation (authenticated)
from app.api.v1.endpoints import evaluation
router.include_router(evaluation.router, tags=["evaluation"])
