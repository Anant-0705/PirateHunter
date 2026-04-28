"""Tests for DMCA notice generation."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from piratehunt.dmca.generator import DMCAGenerator
from piratehunt.dmca.types import DraftNotice, RightsHolderInfo


@pytest.fixture
def rights_holder():
    """Create a test rights holder."""
    return RightsHolderInfo(
        id="test-holder",
        name="Test Sports Rights",
        legal_email="legal@testsports.com",
        address="123 Sports Ave",
        authorized_agent="Legal Team",
        default_language="en",
        signature_block="Signed,\nLegal Department",
    )


@pytest.fixture
def verification_result():
    """Create a test verification result."""
    return {
        "audio_score": 0.97,
        "visual_score": 0.94,
        "combined_score": 0.96,
        "gemini_detected_sport": "cricket",
    }


@pytest.fixture
def candidate():
    """Create a test candidate."""
    return {
        "source_platform": "youtube",
        "source_url": "https://youtube.com/watch?v=test123",
        "discovered_at": "2024-01-15T10:30:00Z",
        "candidate_metadata": {"title": "Test Match"},
    }


@pytest.fixture
def match():
    """Create a test match."""
    return {
        "id": "match-123",
        "name": "Test Cricket Match",
    }


class TestDMCAGenerator:
    """Test DMCA notice generation."""

    @pytest.mark.asyncio
    async def test_generate_creates_draft_notice(
        self, verification_result, candidate, match, rights_holder
    ):
        """Test that generate() creates a valid DraftNotice."""
        generator = DMCAGenerator()
        notice = await generator.generate(
            verification_result, candidate, match, rights_holder
        )

        assert isinstance(notice, DraftNotice)
        assert notice.platform == "youtube"
        assert notice.subject
        assert notice.body
        assert notice.language == "en"
        assert "copyright" in notice.body.lower()

    @pytest.mark.asyncio
    async def test_generate_includes_evidence_summary(
        self, verification_result, candidate, match, rights_holder
    ):
        """Test that generated notice includes evidence summary."""
        generator = DMCAGenerator()
        notice = await generator.generate(
            verification_result, candidate, match, rights_holder
        )

        assert "Audio Fingerprint" in notice.body or "audio" in notice.body.lower()
        assert notice.fingerprint_match_scores["audio"] == 0.97
        assert notice.fingerprint_match_scores["visual"] == 0.94

    @pytest.mark.asyncio
    async def test_generate_falls_back_to_generic_for_unknown_platform(
        self, verification_result, match, rights_holder
    ):
        """Test fallback to generic template for unknown platforms."""
        candidate = {
            "source_platform": "unknown-platform-xyz",
            "source_url": "https://unknown.com/video",
            "discovered_at": "2024-01-15T10:30:00Z",
            "candidate_metadata": {},
        }

        generator = DMCAGenerator()
        notice = await generator.generate(
            verification_result, candidate, match, rights_holder
        )

        # Should still generate notice using generic template
        assert isinstance(notice, DraftNotice)
        assert notice.body
        assert "copyright" in notice.body.lower()

    @pytest.mark.asyncio
    async def test_generate_with_gemini_polish_enabled(
        self, verification_result, candidate, match, rights_holder
    ):
        """Test notice generation with Gemini polishing enabled."""
        generator = DMCAGenerator()

        # Mock Gemini response
        with patch(
            "google.generativeai.GenerativeModel.generate_content"
        ) as mock_gemini:
            mock_response = MagicMock()
            mock_response.text = '{"body": "Polished body text", "subject": "Polished subject"}'
            mock_gemini.return_value = mock_response

            with patch.object(
                generator, "_polish_with_gemini", new_callable=AsyncMock
            ) as mock_polish:
                mock_polish.return_value = {
                    "body": "Polished notice body",
                    "subject": "Polished Subject",
                }

                await generator.generate(
                    verification_result, candidate, match, rights_holder
                )

                # Verify polishing was called if Gemini enabled
                if generator.gemini_enabled:
                    mock_polish.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_without_gemini_key(
        self, verification_result, candidate, match, rights_holder
    ):
        """Test notice generation without Gemini API key."""
        with patch("piratehunt.config.settings.gemini_api_key", None):
            generator = DMCAGenerator()
            notice = await generator.generate(
                verification_result, candidate, match, rights_holder
            )

            # Should still generate notice, just without polishing
            assert isinstance(notice, DraftNotice)
            assert notice.gemini_polish_applied is False

    @pytest.mark.asyncio
    async def test_generate_includes_recipient_email(
        self, verification_result, candidate, match, rights_holder
    ):
        """Test that generated notice includes recipient email."""
        generator = DMCAGenerator()
        notice = await generator.generate(
            verification_result, candidate, match, rights_holder
        )

        # YouTube notice should have copyright@youtube.com
        assert notice.recipient_email_or_form_url
        assert "@" in notice.recipient_email_or_form_url or "youtube" in notice.recipient_email_or_form_url.lower()

    @pytest.mark.asyncio
    async def test_evidence_summary_building(self, verification_result):
        """Test evidence summary generation."""
        generator = DMCAGenerator()
        summary = generator._build_evidence_summary(verification_result)

        assert "97" in summary  # audio score
        assert "94" in summary  # visual score
        assert "96" in summary  # combined score
        assert "fingerprint" in summary.lower()

    def test_platform_recipient_email_mapping(self, rights_holder):
        """Test platform-to-email mapping."""
        generator = DMCAGenerator()

        test_cases = {
            "youtube": "copyright@youtube.com",
            "telegram": "abuse@telegram.org",
            "discord": "abuse@discordapp.com",
            "reddit": "dmca-notice@reddit.com",
            "twitter": "legal@twitter.com",
            "cloudflare": "abuse@cloudflare.com",
            "unknown": rights_holder.legal_email,  # Falls back to rights holder email
        }

        for platform, expected_email in test_cases.items():
            email = generator._get_recipient_email(platform, rights_holder)
            assert email == expected_email, f"Wrong email for {platform}: {email}"

    @pytest.mark.asyncio
    async def test_generate_with_multiple_platforms(
        self, verification_result, match, rights_holder
    ):
        """Test generation for multiple platform candidates."""
        platforms = ["youtube", "telegram", "discord", "reddit", "twitter"]

        generator = DMCAGenerator()

        for platform in platforms:
            candidate = {
                "source_platform": platform,
                "source_url": f"https://{platform}.com/video",
                "discovered_at": "2024-01-15T10:30:00Z",
                "candidate_metadata": {},
            }

            notice = await generator.generate(
                verification_result, candidate, match, rights_holder
            )

            assert notice.platform == platform
            assert notice.body
            assert "copyright" in notice.body.lower()
