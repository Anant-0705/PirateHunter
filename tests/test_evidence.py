from __future__ import annotations

from datetime import datetime
from uuid import uuid4

import pytest
from PIL import Image

from piratehunt.db.models import CandidateStatus, CandidateStream
from piratehunt.verification.evidence import (
    EvidenceCollector,
    GCSEvidenceStorage,
    LocalEvidenceStorage,
)
from piratehunt.verification.types import SampledClip


@pytest.mark.asyncio
async def test_local_evidence_storage_writes_files(workspace_tmp):
    frame = workspace_tmp / "frame.png"
    Image.new("RGB", (16, 16), "red").save(frame)
    clip = workspace_tmp / "clip.mp4"
    clip.write_bytes(b"video")
    candidate = CandidateStream(
        id=uuid4(),
        match_id=uuid4(),
        source_platform="web",
        source_url="https://example.com/video.mp4",
        discovered_at=datetime.utcnow(),
        discovered_by_agent="web",
        candidate_metadata={},
        confidence_hint=0.5,
        status=CandidateStatus.discovered,
    )
    collector = EvidenceCollector(
        storage=LocalEvidenceStorage(workspace_tmp / "evidence"),
        work_dir=workspace_tmp / "work",
    )

    artifact = await collector.collect(
        candidate,
        SampledClip(path=clip, duration=12.0, source_format="mp4", sampler_used="test"),
        [frame],
        {"audio_count": 1},
        {"combined_score": 1.0},
        None,
    )

    assert artifact.artifact_id
    assert (workspace_tmp / "evidence" / artifact.artifact_id / "manifest.json").exists()
    assert (workspace_tmp / "evidence" / artifact.artifact_id / "audio_waveform.png").exists()


def test_gcs_evidence_storage_uses_client(workspace_tmp):
    calls: list[tuple[str, str]] = []

    class FakeBlob:
        def __init__(self, name: str) -> None:
            self.name = name

        def upload_from_filename(self, filename: str) -> None:
            calls.append((self.name, filename))

    class FakeBucket:
        def blob(self, name: str) -> FakeBlob:
            return FakeBlob(name)

    class FakeClient:
        def bucket(self, name: str) -> FakeBucket:
            assert name == "bucket"
            return FakeBucket()

    storage = GCSEvidenceStorage(bucket_name="bucket", client=FakeClient())
    file_path = workspace_tmp / "manifest.json"
    file_path.write_text("{}", encoding="utf-8")

    import asyncio

    uri = asyncio.run(storage.save(file_path, "artifact/manifest.json"))

    assert uri == "gs://bucket/artifact/manifest.json"
    assert calls == [("artifact/manifest.json", str(file_path))]
