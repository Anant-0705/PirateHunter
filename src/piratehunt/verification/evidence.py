from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse

import httpx
from PIL import Image, ImageDraw

from piratehunt.config import settings
from piratehunt.db.models import CandidateStream
from piratehunt.verification.types import EvidenceArtifact, GeminiVerificationSignal, SampledClip

logger = logging.getLogger(__name__)


class EvidenceStorage(Protocol):
    """Storage backend protocol for evidence artifacts."""

    async def save(self, local_path: Path, object_name: str) -> str:
        """Save a local file and return its URI."""


class LocalEvidenceStorage:
    """Filesystem-backed evidence storage."""

    def __init__(self, root_dir: Path | None = None) -> None:
        self.root_dir = root_dir or Path(settings.evidence_local_dir)

    async def save(self, local_path: Path, object_name: str) -> str:
        destination = self.root_dir / object_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(local_path.read_bytes())
        return str(destination)


class GCSEvidenceStorage:
    """GCS-backed evidence storage."""

    def __init__(self, bucket_name: str | None = None, client: object | None = None) -> None:
        self.bucket_name = bucket_name or settings.gcs_evidence_bucket
        if not self.bucket_name:
            msg = "GCS_EVIDENCE_BUCKET is required for GCS evidence storage"
            raise ValueError(msg)
        if client is None:
            from google.cloud import storage

            client = storage.Client()
        self.client = client

    async def save(self, local_path: Path, object_name: str) -> str:
        bucket = self.client.bucket(self.bucket_name)
        blob = bucket.blob(object_name)
        blob.upload_from_filename(str(local_path))
        return f"gs://{self.bucket_name}/{object_name}"


class EvidenceCollector:
    """Collect and persist verification evidence."""

    def __init__(
        self, storage: EvidenceStorage | None = None, work_dir: Path | None = None
    ) -> None:
        self.storage = storage or build_storage_backend()
        self.work_dir = work_dir or Path(settings.evidence_local_dir) / "_work"

    async def collect(
        self,
        candidate: CandidateStream,
        sampled_clip: SampledClip,
        frames: list[Path],
        fingerprints: dict[str, object],
        scores: dict[str, float],
        gemini_signal: GeminiVerificationSignal | None,
    ) -> EvidenceArtifact:
        """Save keyframes, waveform preview, and manifest evidence."""
        artifact_id = str(uuid.uuid4())
        artifact_dir = self.work_dir / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        storage_uris: dict[str, str] = {}

        for idx, frame in enumerate(frames[:3]):
            storage_uris[f"frame_{idx}"] = await self.storage.save(
                frame,
                f"{artifact_id}/frame_{idx}{frame.suffix or '.png'}",
            )

        waveform_path = artifact_dir / "audio_waveform.png"
        _write_placeholder_waveform(waveform_path)
        storage_uris["audio_waveform"] = await self.storage.save(
            waveform_path,
            f"{artifact_id}/audio_waveform.png",
        )

        manifest_path = artifact_dir / "manifest.json"
        manifest = {
            "candidate_id": str(candidate.id),
            "match_id": str(candidate.match_id),
            "source_url": candidate.source_url,
            "sampled_clip": sampled_clip.model_dump(mode="json"),
            "fingerprints": fingerprints,
            "scores": scores,
            "gemini_signal": gemini_signal.model_dump(mode="json") if gemini_signal else None,
            "whois": await _whois_domain(candidate.source_url),
            "cdn": await _identify_cdn(candidate.source_url),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        storage_uris["manifest"] = await self.storage.save(
            manifest_path, f"{artifact_id}/manifest.json"
        )

        return EvidenceArtifact(artifact_id=artifact_id, storage_uris=storage_uris)


def build_storage_backend() -> EvidenceStorage:
    """Create evidence storage from configuration."""
    if settings.evidence_storage_backend.lower() == "gcs":
        return GCSEvidenceStorage()
    return LocalEvidenceStorage()


def _write_placeholder_waveform(path: Path) -> None:
    image = Image.new("RGB", (640, 160), "white")
    draw = ImageDraw.Draw(image)
    for x in range(0, 640, 8):
        y = 80 + int(50 * (((x // 8) % 7) / 6 - 0.5))
        draw.line((x, 80, x, y), fill="navy", width=2)
    image.save(path)


async def _whois_domain(url: str) -> dict[str, object] | None:
    try:
        import whois  # type: ignore[import-untyped]

        domain = urlparse(url).hostname
        if not domain:
            return None
        data = whois.whois(domain)
        return {
            "domain_name": str(data.get("domain_name")),
            "registrar": str(data.get("registrar")),
        }
    except Exception as exc:
        logger.debug("WHOIS lookup failed for %s: %s", url, exc)
        return None


async def _identify_cdn(url: str) -> dict[str, str] | None:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.head(url, follow_redirects=True)
        headers = {key.lower(): value for key, value in response.headers.items()}
        server = headers.get("server", "")
        cdn = "unknown"
        if "cloudflare" in server.lower() or "cf-ray" in headers:
            cdn = "cloudflare"
        elif "akamai" in server.lower() or "akamai" in headers.get("via", "").lower():
            cdn = "akamai"
        return {"cdn": cdn, "server": server}
    except Exception as exc:
        logger.debug("CDN identification failed for %s: %s", url, exc)
        return None
