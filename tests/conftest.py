from __future__ import annotations

import pytest


@pytest.fixture
def sample_video_path():
    """Return path to sample video fixture, skip if not found."""
    from pathlib import Path

    fixture_path = Path(__file__).parent / "fixtures" / "sample.mp4"
    if not fixture_path.exists():
        pytest.skip("tests/fixtures/sample.mp4 not found. Add a sample video to run this test.")
    return fixture_path
