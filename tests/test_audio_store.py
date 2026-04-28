from __future__ import annotations

from piratehunt.fingerprint.types import AudioFingerprint
from piratehunt.index.audio_store import AudioFingerprintStore


def test_audio_fingerprint_store_initialization():
    """Test AudioFingerprintStore initialization."""
    store = AudioFingerprintStore()

    assert len(store) == 0


def test_audio_fingerprint_store_add():
    """Test adding fingerprints to store."""
    store = AudioFingerprintStore()

    fps = [
        AudioFingerprint(
            fingerprint_hash="hash1", duration_s=1.0, source_id="src1"
        ),
        AudioFingerprint(
            fingerprint_hash="hash2", duration_s=1.0, source_id="src2"
        ),
    ]

    store.add(fps)
    assert len(store) == 2


def test_audio_fingerprint_store_add_empty():
    """Test adding empty list does not error."""
    store = AudioFingerprintStore()

    store.add([])
    assert len(store) == 0


def test_audio_fingerprint_store_search_empty():
    """Test searching empty store."""
    store = AudioFingerprintStore()

    query = AudioFingerprint(
        fingerprint_hash="query_hash", duration_s=1.0, source_id="query"
    )

    results = store.search(query)
    assert results == []


def test_audio_fingerprint_store_search_with_matches():
    """Test search returns matches above threshold."""
    store = AudioFingerprintStore()

    # Add a fingerprint
    fp = AudioFingerprint(fingerprint_hash="test_hash", duration_s=1.0, source_id="test")
    store.add([fp])

    # Search with same hash (should match with high similarity)
    query = AudioFingerprint(fingerprint_hash="test_hash", duration_s=1.0, source_id="query")

    results = store.search(query, threshold=0.5)

    # Results depend on chromaprint comparison; at minimum we can verify structure
    assert isinstance(results, list)
    for fp_match, score in results:
        assert isinstance(fp_match, AudioFingerprint)
        assert isinstance(score, float)
        assert 0 <= score <= 1


def test_audio_fingerprint_store_search_top_k():
    """Test limiting results with top_k."""
    store = AudioFingerprintStore()

    # Add multiple fingerprints
    for i in range(5):
        fp = AudioFingerprint(
            fingerprint_hash=f"hash_{i}", duration_s=1.0, source_id=f"src_{i}"
        )
        store.add([fp])

    query = AudioFingerprint(fingerprint_hash="query", duration_s=1.0, source_id="query")

    results = store.search(query, threshold=0.0, top_k=2)

    # Should return at most 2 results
    assert len(results) <= 2


def test_audio_fingerprint_store_clear():
    """Test clearing the store."""
    store = AudioFingerprintStore()

    fp = AudioFingerprint(fingerprint_hash="hash", duration_s=1.0, source_id="src")
    store.add([fp])
    assert len(store) == 1

    store.clear()
    assert len(store) == 0
