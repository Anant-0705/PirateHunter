from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AudioFingerprint(BaseModel):
    """Chromaprint audio fingerprint with metadata."""

    fingerprint_hash: str = Field(..., description="Chromaprint fingerprint hash")
    duration_s: float = Field(..., description="Duration of audio chunk in seconds")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_id: str = Field(..., description="Identifier of the media source")


class VisualFingerprint(BaseModel):
    """Perceptual hash fingerprints for a single video keyframe."""

    phash: str = Field(..., description="64-bit pHash as hex string")
    dhash: str = Field(..., description="64-bit dHash as hex string")
    frame_index: int = Field(..., description="Index of frame in sequence")
    source_id: str = Field(..., description="Identifier of the media source")


class FingerprintBundle(BaseModel):
    """Complete set of fingerprints for a media segment."""

    source_id: str = Field(..., description="Identifier of the media source")
    audio_fingerprints: list[AudioFingerprint] = Field(
        default_factory=list, description="Audio fingerprints"
    )
    visual_fingerprints: list[VisualFingerprint] = Field(
        default_factory=list, description="Visual fingerprints"
    )
