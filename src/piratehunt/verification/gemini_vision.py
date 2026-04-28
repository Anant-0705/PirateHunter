from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from piratehunt.config import settings
from piratehunt.verification.types import GeminiVerificationSignal

logger = logging.getLogger(__name__)


class GeminiVisionVerifier:
    """Gemini Vision secondary verification signal."""

    def __init__(self, *, api_key: str | None = None, model_name: str | None = None) -> None:
        self.api_key = api_key or settings.gemini_api_key
        self.model_name = model_name or settings.gemini_model

    async def verify(
        self,
        frame_paths: list[Path],
        expected_sport: str | None = None,
    ) -> GeminiVerificationSignal | None:
        """Verify sampled frames with Gemini, returning None on fail-soft errors."""
        if not self.api_key:
            logger.warning("Gemini Vision enabled but GEMINI_API_KEY is missing")
            return None
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._verify_sync, frame_paths, expected_sport),
                timeout=settings.gemini_timeout_seconds,
            )
        except Exception as exc:
            logger.warning("Gemini Vision verification failed: %s", exc)
            return None

    def _verify_sync(
        self,
        frame_paths: list[Path],
        expected_sport: str | None,
    ) -> GeminiVerificationSignal:
        import google.generativeai as genai
        from PIL import Image

        genai.configure(api_key=self.api_key)
        model = genai.GenerativeModel(self.model_name)
        prompt = (
            "Analyze these sampled video frames. Return strict JSON with keys: "
            "is_sports_content (boolean), detected_sport (string or null), "
            "broadcaster_logos_detected (array of strings), confidence (0-1). "
            f"Expected sport: {expected_sport or 'unknown'}."
        )
        images = [Image.open(path) for path in frame_paths[:3]]
        response = model.generate_content([prompt, *images])
        raw = str(response.text)
        return parse_gemini_response(raw)


def parse_gemini_response(raw_response: str) -> GeminiVerificationSignal:
    """Parse Gemini JSON output, tolerating markdown fences."""
    cleaned = raw_response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    data = json.loads(cleaned)
    return GeminiVerificationSignal(
        is_sports_content=bool(data["is_sports_content"]),
        detected_sport=data.get("detected_sport"),
        broadcaster_logos_detected=list(data.get("broadcaster_logos_detected") or []),
        confidence=float(data.get("confidence", 0.0)),
        raw_response=raw_response,
    )


class MockGeminiVisionVerifier:
    """Deterministic Gemini verifier for tests."""

    def __init__(self, fixture_map: dict[str, GeminiVerificationSignal | Exception | str]) -> None:
        self.fixture_map = fixture_map

    async def verify(
        self,
        frame_paths: list[Path],
        expected_sport: str | None = None,
    ) -> GeminiVerificationSignal | None:
        key = expected_sport or "default"
        result = self.fixture_map.get(key) or self.fixture_map.get("default")
        if isinstance(result, Exception):
            logger.warning("Mock Gemini verification failed: %s", result)
            return None
        if isinstance(result, str):
            try:
                return parse_gemini_response(result)
            except Exception as exc:
                logger.warning("Mock Gemini response parsing failed: %s", exc)
                return None
        return result
