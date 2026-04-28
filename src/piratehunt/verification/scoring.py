from __future__ import annotations

from typing import Literal

from piratehunt.verification.types import GeminiVerificationSignal

Verdict = Literal["pirate", "clean", "inconclusive"]


def combined_match_score(
    audio_score: float,
    visual_score: float,
    weights: tuple[float, float],
) -> float:
    """Compute a normalized weighted match score."""
    audio_weight, visual_weight = weights
    total = audio_weight + visual_weight
    if total <= 0:
        return 0.0
    score = ((audio_score * audio_weight) + (visual_score * visual_weight)) / total
    return max(0.0, min(1.0, score))


def verdict_from_scores(
    combined: float,
    *,
    gemini_signal: GeminiVerificationSignal | None = None,
    audio_threshold: float,
    visual_threshold: float,
    combined_threshold: float,
    clean_threshold: float = 0.4,
) -> Verdict:
    """Classify a candidate using match scores and optional Gemini signal."""
    if combined >= combined_threshold:
        return "pirate"
    if combined < clean_threshold:
        return "clean"

    if gemini_signal is not None and gemini_signal.is_sports_content:
        boost = 0.08 if gemini_signal.broadcaster_logos_detected else 0.04
        boosted = min(1.0, combined + (gemini_signal.confidence * boost))
        if boosted >= combined_threshold:
            return "pirate"

    return "inconclusive"
