"""Pydantic V2 schemas for the Embedding & Indexing layer."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IndexingJobResponse(BaseModel):
    """Indexing job status returned to clients."""

    id: str = Field(..., description="Job UUID")
    document_id: str | None = Field(None, description="Document UUID")
    collection_name: str = Field(..., description="Target Milvus collection")
    status: str = Field(..., description="Job status")
    progress: float = Field(0.0, description="Progress percentage")
    current_stage: str | None = Field(None, description="Current processing stage")
    total_chunks: int = Field(0, description="Total chunks to index")
    processed_chunks: int = Field(0, description="Successfully indexed chunks")
    failed_chunks: int = Field(0, description="Failed chunks")
    error_message: str | None = Field(None, description="Error details")
    retry_count: int = Field(0, description="Retry attempts")
    max_retries: int = Field(3, description="Maximum retries")
    started_at: datetime | None = Field(None)
    completed_at: datetime | None = Field(None)
    created_at: datetime = Field(...)
    model_config = {"from_attributes": True}


class IndexingJobCreate(BaseModel):
    """Request to start an indexing job."""

    document_id: str = Field(..., description="Document UUID to index")
    collection_name: str = Field("chunks", description="Target collection name")
    reindex: bool = Field(False, description="Re-index if already indexed")


class CollectionResponse(BaseModel):
    """Collection metadata returned to clients."""

    id: str = Field(..., description="Collection UUID (PostgreSQL)")
    name: str = Field(..., description="Collection name (Milvus)")
    display_name: str | None = Field(None)
    dimension: int = Field(..., description="Vector dimension")
    metric_type: str = Field("COSINE", description="Distance metric")
    vector_count: int = Field(0, description="Number of vectors")
    status: str = Field("active", description="Collection status")
    version: int = Field(1, description="Schema version")
    embedding_model: str = Field(..., description="Embedding model name")
    description: str | None = Field(None)
    created_at: datetime = Field(...)
    model_config = {"from_attributes": True}


class CollectionDetailResponse(CollectionResponse):
    """Detailed collection info including Milvus stats."""

    milvus_stats: dict[str, Any] = Field(default_factory=dict)
    index_info: list[dict[str, Any]] = Field(default_factory=list)


class IndexStatsResponse(BaseModel):
    """Aggregated indexing statistics."""

    total_jobs: int = Field(0)
    active_jobs: int = Field(0)
    completed_jobs: int = Field(0)
    failed_jobs: int = Field(0)
    total_chunks_indexed: int = Field(0)
    total_failed_chunks: int = Field(0)
    total_collections: int = Field(0)
    total_vectors: int = Field(0)
    cache_hit_rate: float = Field(0.0)
