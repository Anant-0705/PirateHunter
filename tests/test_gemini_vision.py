from __future__ import annotations

import pytest

from piratehunt.verification.gemini_vision import MockGeminiVisionVerifier
from piratehunt.verification.types import GeminiVerificationSignal


@pytest.mark.asyncio
async def test_mock_gemini_happy_path(workspace_tmp):
    signal = GeminiVerificationSignal(
        is_sports_content=True,
        detected_sport="cricket",
        broadcaster_logos_detected=["Mock Sports"],
        confidence=0.91,
        raw_response="{}",
    )
    verifier = MockGeminiVisionVerifier({"default": signal})

    result = await verifier.verify([workspace_tmp / "frame.png"])

    assert result == signal


@pytest.mark.asyncio
async def test_mock_gemini_timeout_returns_none(workspace_tmp):
    verifier = MockGeminiVisionVerifier({"default": TimeoutError("timeout")})

    assert await verifier.verify([workspace_tmp / "frame.png"]) is None


@pytest.mark.asyncio
async def test_mock_gemini_malformed_json_returns_none(workspace_tmp):
    verifier = MockGeminiVisionVerifier({"default": "not json"})

    assert await verifier.verify([workspace_tmp / "frame.png"]) is None
