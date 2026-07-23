"""Enterprise Retrieval Engine — dense, BM25, hybrid, and parent-child retrieval with reranking.

Provides high-quality retrieval for enterprise RAG systems.
"""

from app.retrieval.schemas import (
    RetrievalRequest,
    RetrievalResult,
    RetrievedChunk,
    Citation,
    RetrievalMetrics,
)
from app.retrieval.retrievers.base import Retriever
from app.retrieval.retrievers.dense import DenseRetriever
from app.retrieval.retrievers.bm25 import BM25Retriever
from app.retrieval.retrievers.hybrid import HybridRetriever
from app.retrieval.retrievers.parent_child import ParentChildRetriever
from app.retrieval.rerankers.base import Reranker
from app.retrieval.services.retrieval_service import RetrievalService

__all__ = [
    "RetrievalRequest",
    "RetrievalResult",
    "RetrievedChunk",
    "Citation",
    "RetrievalMetrics",
    "Retriever",
    "DenseRetriever",
    "BM25Retriever",
    "HybridRetriever",
    "ParentChildRetriever",
    "Reranker",
    "RetrievalService",
]
