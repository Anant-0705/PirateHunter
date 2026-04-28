"""Tests for DMCA notice templates."""

from __future__ import annotations

from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader


@pytest.fixture
def jinja_env():
    """Create Jinja2 environment for templates."""
    templates_path = Path(__file__).parent.parent / "src" / "piratehunt" / "dmca" / "templates"
    return Environment(
        loader=FileSystemLoader(str(templates_path)),
        trim_blocks=True,
        lstrip_blocks=True,
    )


@pytest.fixture
def template_context():
    """Provide test context for template rendering."""
    return {
        "match_name": "Test Cricket Match",
        "infringing_url": "https://youtube.com/watch?v=test123",
        "source_platform": "youtube",
        "discovered_at": "2024-01-15T10:30:00Z",
        "candidate_title": "Live Match Broadcast",
        "candidate_metadata": {"duration": 3600, "title": "Test Match"},
        "audio_score": 0.97,
        "visual_score": 0.94,
        "combined_score": 0.96,
        "gemini_verdict": "Cricket",
        "evidence_summary": "Audio score: 97%. Visual score: 94%. Combined: 96%.",
        "rights_holder_name": "Test Sports Inc.",
        "rights_holder_email": "legal@testsports.com",
        "rights_holder_address": "123 Sports Ave, Demo City",
        "authorized_agent": "Legal Department",
        "submitted_at": "2024-01-15T10:35:00Z",
        "timestamp": "2024-01-15T10:35:00Z",
    }


class TestDMCATemplates:
    """Test DMCA notice template rendering."""

    @pytest.mark.parametrize(
        "template_name",
        [
            "generic_host.j2",
            "youtube.j2",
            "telegram.j2",
            "discord.j2",
            "reddit.j2",
            "twitter.j2",
            "cloudflare.j2",
        ],
    )
    def test_template_renders_without_error(
        self, jinja_env, template_context, template_name
    ):
        """Test that each template renders successfully."""
        template = jinja_env.get_template(template_name)
        rendered = template.render(**template_context)
        assert len(rendered) > 0
        assert "copyright" in rendered.lower()

    @pytest.mark.parametrize(
        "template_name",
        [
            "generic_host.j2",
            "youtube.j2",
            "telegram.j2",
            "discord.j2",
            "reddit.j2",
            "twitter.j2",
            "cloudflare.j2",
        ],
    )
    def test_template_includes_required_dmca_elements(
        self, jinja_env, template_context, template_name
    ):
        """Test that templates include required DMCA legal language."""
        template = jinja_env.get_template(template_name)
        rendered = template.render(**template_context).lower()

        # Check for required DMCA elements
        required_elements = [
            "copyright",
            "infringing",
            "good faith",
            "penalty of perjury",
        ]

        for element in required_elements:
            assert element in rendered, f"Missing required element: {element}"

    def test_youtube_template_includes_platform_specific_info(
        self, jinja_env, template_context
    ):
        """Test YouTube template has platform-specific content."""
        template = jinja_env.get_template("youtube.j2")
        rendered = template.render(**template_context).lower()
        assert "youtube" in rendered or "platform" in rendered

    def test_generic_template_is_fallback(self, jinja_env, template_context):
        """Test that generic template can serve as fallback."""
        generic = jinja_env.get_template("generic_host.j2")
        rendered = generic.render(**template_context)
        assert "DMCA" in rendered or "copyright" in rendered.lower()

    def test_template_with_missing_context_fields(self, jinja_env):
        """Test that templates handle missing context fields gracefully."""
        minimal_context = {
            "match_name": "Test Match",
            "infringing_url": "https://example.com",
        }
        template = jinja_env.get_template("generic_host.j2")
        # Should not raise exception even with missing fields
        rendered = template.render(**minimal_context)
        assert len(rendered) > 0

    def test_template_variable_substitution(self, jinja_env, template_context):
        """Test that template variables are properly substituted."""
        template = jinja_env.get_template("generic_host.j2")
        rendered = template.render(**template_context)
        assert "Test Cricket Match" in rendered
        assert "https://youtube.com/watch?v=test123" in rendered
        assert "Test Sports Inc." in rendered
