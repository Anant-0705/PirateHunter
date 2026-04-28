from __future__ import annotations

import pytest

from piratehunt.verification.scoring import combined_match_score, verdict_from_scores
from piratehunt.verification.types import GeminiVerificationSignal


def test_combined_match_score_normalizes_weights():
    assert combined_match_score(1.0, 0.5, (0.6, 0.4)) == pytest.approx(0.8)


@pytest.mark.parametrize(
    ("combined", "expected"),
    [
        (0.85, "pirate"),
        (0.84, "inconclusive"),
        (0.4, "inconclusive"),
        (0.39, "clean"),
    ],
)
def test_verdict_threshold_edges(combined, expected):
    assert (
        verdict_from_scores(
            combined,
            audio_threshold=0.5,
            visual_threshold=10.0,
            combined_threshold=0.85,
            clean_threshold=0.4,
        )
        == expected
    )


def test_gemini_can_push_borderline_to_pirate():
    signal = GeminiVerificationSignal(
        is_sports_content=True,
        detected_sport="cricket",
        broadcaster_logos_detected=["Mock Sports"],
        confidence=1.0,
        raw_response="{}",
    )

    assert (
        verdict_from_scores(
            0.78,
            gemini_signal=signal,
            audio_threshold=0.5,
            visual_threshold=10.0,
            combined_threshold=0.85,
            clean_threshold=0.4,
        )
        == "pirate"
    )


def test_missing_gemini_signal_keeps_borderline_inconclusive():
    assert (
        verdict_from_scores(
            0.78,
            gemini_signal=None,
            audio_threshold=0.5,
            visual_threshold=10.0,
            combined_threshold=0.85,
            clean_threshold=0.4,
        )
        == "inconclusive"
    )
