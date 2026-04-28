from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class IngestionRequested(BaseModel):
    """Redis stream event requesting ingestion for a source URL."""

    match_id: UUID
    source_url: str


class IngestionProgress(BaseModel):
    """Redis stream event emitted periodically during ingestion."""

    match_id: UUID
    chunks_processed: int = Field(ge=0)


class IngestionCompleted(BaseModel):
    """Redis stream event emitted after ingestion finishes."""

    match_id: UUID
    total_chunks: int = Field(ge=0)


class IngestionFailed(BaseModel):
    """Redis stream event emitted when ingestion fails."""

    match_id: UUID
    error: str
