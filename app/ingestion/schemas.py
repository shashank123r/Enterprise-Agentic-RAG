"""Pydantic V2 schemas for the Enterprise Document Intelligence Pipeline."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DocumentResponse(BaseModel):
    """Document metadata returned to clients."""

    id: str = Field(..., description="Document UUID")
    filename: str = Field(..., description="Storage filename")
    original_filename: str = Field(..., description="Original upload filename")
    mime_type: str = Field(..., description="Detected MIME type")
    size_bytes: int = Field(..., description="File size in bytes")
    checksum: str = Field(..., description="SHA-256 content checksum")
    status: str = Field(..., description="Ingestion status")
    title: str | None = Field(None, description="Extracted document title")
    author: str | None = Field(None, description="Extracted author")
    language: str | None = Field(None, description="Detected language code")
    page_count: int = Field(0, description="Number of pages")
    table_count: int = Field(0, description="Number of extracted tables")
    image_count: int = Field(0, description="Number of extracted images")
    chunk_count: int = Field(0, description="Number of chunks")
    ocr_used: bool = Field(False, description="Whether OCR was applied")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Custom document metadata",
        validation_alias="custom_metadata",
    )
    current_version: int = Field(1, description="Current version number")
    is_deleted: bool = Field(False, description="Soft delete flag")
    created_at: datetime = Field(..., description="Upload timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentListResponse(BaseModel):
    """Paginated document list response."""

    items: list[DocumentResponse]
    total: int
    page: int
    size: int
    pages: int


class IngestionStatusResponse(BaseModel):
    """Current status of an ingestion job."""

    job_id: str = Field(..., description="Job UUID", validation_alias="id")
    document_id: str = Field(..., description="Document UUID")
    status: str = Field(..., description="Job status")
    progress: float = Field(0.0, description="Progress percentage (0-100)")
    current_stage: str | None = Field(None, description="Current processing stage")
    error_message: str | None = Field(None, description="Error details if failed")
    retry_count: int = Field(0, description="Number of retries so far")
    max_retries: int = Field(3, description="Maximum retry attempts")
    started_at: datetime | None = Field(None, description="Processing start time")
    completed_at: datetime | None = Field(None, description="Completion time")
    created_at: datetime = Field(..., description="Job creation time")

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentUploadResponse(BaseModel):
    """Response after a successful document upload."""

    document: DocumentResponse = Field(..., description="Created document")
    job: IngestionStatusResponse = Field(..., description="Ingestion job")


class DocumentReplaceResponse(BaseModel):
    """Response after replacing a document."""

    document: DocumentResponse = Field(..., description="Updated document")
    job: IngestionStatusResponse = Field(..., description="New ingestion job")
    new_version: int = Field(..., description="New version number")


class DocumentVersionResponse(BaseModel):
    """Document version history entry."""

    id: str = Field(..., description="Version UUID")
    version_number: int = Field(..., description="Version number")
    filename: str = Field(..., description="Version filename")
    size_bytes: int = Field(..., description="File size")
    checksum: str = Field(..., description="Content checksum")
    changes: str | None = Field(None, description="Change description")
    created_at: datetime = Field(..., description="Version creation time")

    model_config = {"from_attributes": True}


class ChunkResponse(BaseModel):
    """Document chunk response."""

    id: str = Field(..., description="Chunk UUID")
    chunk_index: int = Field(..., description="Position in document")
    content: str = Field(..., description="Chunk text content")
    page_number: int | None = Field(None, description="Source page")
    section_title: str | None = Field(None, description="Section heading")
    chunk_type: str = Field("text", description="Type of chunk")
    language: str | None = Field(None, description="Detected language")
    token_count: int = Field(0, description="Token count")
    char_count: int = Field(0, description="Character count")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Chunk metadata",
        validation_alias="custom_metadata",
    )

    model_config = {"from_attributes": True, "populate_by_name": True}


class TableResponse(BaseModel):
    """Extracted table response."""

    id: str = Field(..., description="Table UUID")
    page_number: int | None = Field(None, description="Source page")
    table_index: int = Field(..., description="Table position")
    caption: str | None = Field(None, description="Table caption")
    csv_representation: str = Field(..., description="CSV format data")
    html_representation: str | None = Field(None, description="HTML format")
    row_count: int = Field(0, description="Number of rows")
    column_count: int = Field(0, description="Number of columns")

    model_config = {"from_attributes": True}


class ImageResponse(BaseModel):
    """Extracted image response."""

    id: str = Field(..., description="Image UUID")
    page_number: int | None = Field(None, description="Source page")
    image_index: int = Field(..., description="Image position")
    image_path: str = Field(..., description="Path to stored image")
    caption: str | None = Field(None, description="Auto-generated caption")
    alt_text: str | None = Field(None, description="Alt text")
    width: int | None = Field(None, description="Image width in pixels")
    height: int | None = Field(None, description="Image height in pixels")
    format: str | None = Field(None, description="Image format")

    model_config = {"from_attributes": True}


class ExtractTextResponse(BaseModel):
    """Response for extracted text download."""

    document_id: str = Field(..., description="Document UUID")
    filename: str = Field(..., description="Original filename")
    total_chunks: int = Field(..., description="Total chunk count")
    total_characters: int = Field(..., description="Total extracted text length")
    text: str = Field(..., description="Full extracted text (all chunks concatenated)")


class DocumentStatsResponse(BaseModel):
    """Document processing statistics."""

    document_id: str
    filename: str
    mime_type: str
    status: str
    processing_time_ms: int = 0
    page_count: int = 0
    table_count: int = 0
    image_count: int = 0
    chunk_count: int = 0
    ocr_used: bool = False
    language: str | None = None
    extraction_errors: list[dict[str, Any]] = Field(
        default_factory=list, description="Non-fatal extraction errors"
    )

    model_config = {"from_attributes": True}
