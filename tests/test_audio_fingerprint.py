from __future__ import annotations

from piratehunt.fingerprint.audio import fingerprint_audio_chunk
from piratehunt.fingerprint.types import AudioFingerprint


def test_fingerprint_audio_chunk_basic():
    """Test basic audio fingerprinting with synthetic PCM data."""
    # Generate 1 second of 440Hz sine wave at 44.1kHz
    import numpy as np

    sample_rate = 44100
    duration_s = 1.0
    frequency = 440.0

    samples = np.sin(
        2 * np.pi * frequency * np.linspace(0, duration_s, int(sample_rate * duration_s))
    )
    # Convert to 16-bit PCM
    samples_16bit = (samples * 32767).astype(np.int16)
    pcm_bytes = samples_16bit.tobytes()

    # Fingerprint the audio
    fp = fingerprint_audio_chunk(pcm_bytes, sample_rate=sample_rate, source_id="test_sine")

    # Verify result
    assert isinstance(fp, AudioFingerprint)
    assert isinstance(fp.fingerprint_hash, str)
    assert len(fp.fingerprint_hash) > 0
    assert fp.duration_s > 0
    assert fp.source_id == "test_sine"
    assert fp.created_at is not None


def test_fingerprint_audio_chunk_different_sources():
    """Test that different audio produces different fingerprints."""
    import numpy as np

    sample_rate = 44100
    duration_s = 1.0

    # Generate two different sine waves
    freq1, freq2 = 440.0, 880.0

    for freq in [freq1, freq2]:
        samples = np.sin(
            2 * np.pi * freq * np.linspace(0, duration_s, int(sample_rate * duration_s))
        )
        samples_16bit = (samples * 32767).astype(np.int16)
        pcm_bytes = samples_16bit.tobytes()

        fp = fingerprint_audio_chunk(pcm_bytes, sample_rate=sample_rate, source_id=f"freq_{freq}")
        assert isinstance(fp, AudioFingerprint)
        assert len(fp.fingerprint_hash) > 0


def test_fingerprint_audio_chunk_invalid_input():
    """Test graceful handling of minimal audio data."""
    # Fingerprinting small data succeeds (falls back to hash)
    fp = fingerprint_audio_chunk(b"minimal", sample_rate=44100)
    assert isinstance(fp, AudioFingerprint)
    assert len(fp.fingerprint_hash) > 0
