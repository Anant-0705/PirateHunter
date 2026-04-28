from __future__ import annotations

from piratehunt.fingerprint.types import AudioFingerprint
from piratehunt.index.audio_store import chromaprint_similarity


def test_identical_fingerprints_score_one():
    fp = AudioFingerprint(fingerprint_hash="\x00" * 16, duration_s=1.0, source_id="a")

    assert chromaprint_similarity(fp, fp) == 1.0


def test_randomized_fingerprints_score_low():
    left = AudioFingerprint(fingerprint_hash="\x00" * 16, duration_s=1.0, source_id="a")
    right = AudioFingerprint(fingerprint_hash="\xff" * 16, duration_s=1.0, source_id="b")

    assert chromaprint_similarity(left, right) < 0.2
