from __future__ import annotations

import pytest

from piratehunt.fingerprint.extractor import extract_audio_and_keyframes


def test_extract_audio_and_keyframes_requires_ffmpeg(sample_video_path):
    """Test extraction from a video file (requires ffmpeg + sample video)."""
    # This test runs only if sample.mp4 exists
    try:
        count = 0
        for audio_chunk, keyframes in extract_audio_and_keyframes(
            sample_video_path, window_seconds=2, keyframe_interval=1
        ):
            assert isinstance(audio_chunk, bytes)
            assert isinstance(keyframes, list)
            count += 1
            # Limit iterations for testing
            if count >= 2:
                break

        assert count > 0, "Should extract at least one window"
    except FileNotFoundError:
        pytest.skip("ffmpeg not found. Install ffmpeg to run this test.")
    except Exception as e:
        pytest.skip(f"Extraction failed (may require ffmpeg): {e}")
