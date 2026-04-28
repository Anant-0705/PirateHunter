from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

import google.generativeai as genai
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from piratehunt.config import settings
from piratehunt.dmca.types import DraftNotice, RightsHolderInfo

logger = logging.getLogger(__name__)


class DMCAGenerator:
    """Generate DMCA notices with optional Gemini polishing."""

    def __init__(self):
        """Initialize the DMCA generator with Jinja2 environment."""
        templates_path = Path(__file__).parent / "templates"
        self.env = Environment(
            loader=FileSystemLoader(str(templates_path)),
            trim_blocks=True,
            lstrip_blocks=True,
        )

        # Configure Gemini if API key is available
        if settings.gemini_api_key:
            genai.configure(api_key=settings.gemini_api_key)
            self.gemini_enabled = True
        else:
            self.gemini_enabled = False
            logger.warning("Gemini API key not configured; DMCA polishing disabled")

    async def generate(
        self,
        verification_result: dict,
        candidate: dict,
        match: dict,
        rights_holder: RightsHolderInfo,
    ) -> DraftNotice:
        """
        Generate a DMCA draft notice for a verified pirate candidate.

        Args:
            verification_result: Verification result with scores and metadata
            candidate: Candidate stream with platform and URL info
            match: Original match with name and other details
            rights_holder: Rights holder information

        Returns:
            DraftNotice with rendered template and optionally polished content
        """
        platform = candidate.get("source_platform", "unknown").lower()
        infringing_url = candidate.get("source_url", "")

        # Prepare context for template rendering
        context = {
            "match_name": match.get("name", "Unknown Content"),
            "infringing_url": infringing_url,
            "source_platform": platform,
            "discovered_at": candidate.get("discovered_at", datetime.utcnow()).isoformat(),
            "candidate_title": candidate.get("candidate_metadata", {}).get("title", ""),
            "candidate_metadata": candidate.get("candidate_metadata", {}),
            "audio_score": verification_result.get("audio_score", 0),
            "visual_score": verification_result.get("visual_score", 0),
            "combined_score": verification_result.get("combined_score", 0),
            "gemini_verdict": verification_result.get("gemini_detected_sport", "Sports Content"),
            "evidence_summary": self._build_evidence_summary(verification_result),
            "rights_holder_name": rights_holder.name,
            "rights_holder_email": rights_holder.legal_email,
            "rights_holder_address": rights_holder.address,
            "authorized_agent": rights_holder.authorized_agent,
            "submitted_at": datetime.utcnow().isoformat(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Pick template: try platform-specific, fall back to generic
        template_name = f"{platform}.j2"
        try:
            template = self.env.get_template(template_name)
            logger.debug(f"Using platform-specific template: {template_name}")
        except TemplateNotFound:
            logger.debug(
                f"Platform template {template_name} not found, falling back to generic_host.j2"
            )
            template = self.env.get_template("generic_host.j2")

        # Render the template
        rendered_body = template.render(**context)

        # Generate subject line
        subject = f"DMCA Takedown Notice: {match.get('name', 'Infringing Content')}"

        # Optionally polish with Gemini
        gemini_applied = False
        if self.gemini_enabled and settings.dmca_gemini_polish_enabled:
            try:
                polished_result = await self._polish_with_gemini(
                    rendered_body, platform, subject, rights_holder.default_language
                )
                rendered_body = polished_result["body"]
                subject = polished_result["subject"]
                gemini_applied = True
                logger.debug(f"Applied Gemini polishing for {platform}")
            except asyncio.TimeoutError:
                logger.warning("Gemini polishing timed out; using unpolished draft")
            except Exception as e:
                logger.warning(f"Gemini polishing failed: {e}; using unpolished draft")

        # Build recipient email based on platform
        recipient_email = self._get_recipient_email(platform, rights_holder)

        return DraftNotice(
            platform=platform,
            recipient_email_or_form_url=recipient_email,
            subject=subject,
            body=rendered_body,
            language=rights_holder.default_language,
            gemini_polish_applied=gemini_applied,
            evidence_uris=[],  # Can be populated from verification_result
            fingerprint_match_scores={
                "audio": verification_result.get("audio_score", 0),
                "visual": verification_result.get("visual_score", 0),
                "combined": verification_result.get("combined_score", 0),
            },
        )

    async def _polish_with_gemini(
        self,
        draft_body: str,
        platform: str,
        subject: str,
        language: str,
    ) -> dict[str, str]:
        """
        Use Gemini to polish and optimize the DMCA notice.

        Args:
            draft_body: Initial rendered notice body
            platform: Target platform (youtube, telegram, etc.)
            subject: Initial subject line
            language: Target language

        Returns:
            Dictionary with 'body' and 'subject' keys containing polished content
        """
        prompt = f"""You are a legal expert specializing in DMCA takedown notices.
Improve the following DMCA notice for {platform} platform compliance.
Target language: {language}

Requirements:
1. Maintain all legally required DMCA elements (good faith belief, penalty of perjury, etc.)
2. Optimize language for {platform}'s known abuse-form requirements
3. If language is not English, translate key sections appropriately
4. Create a sharp, compelling subject line
5. Ensure contact information is prominently featured

Current draft:
---
{draft_body}
---

Respond with JSON containing:
{{
  "body": "improved notice body",
  "subject": "new subject line",
  "language_applied": "{language}"
}}"""

        try:
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = await asyncio.wait_for(
                asyncio.to_thread(model.generate_content, prompt),
                timeout=settings.dmca_generation_timeout_seconds - 5,
            )

            # Parse response
            response_text = response.text
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            import json
            result = json.loads(response_text)
            return {
                "body": result.get("body", draft_body),
                "subject": result.get("subject", f"DMCA Takedown Notice - {platform}"),
            }
        except asyncio.TimeoutError as e:
            raise asyncio.TimeoutError("Gemini request timed out") from e
        except Exception as e:
            raise RuntimeError(f"Gemini processing failed: {e}") from e

    def _build_evidence_summary(self, verification_result: dict) -> str:
        """Build a text summary of fingerprint evidence."""
        audio = verification_result.get("audio_score", 0)
        visual = verification_result.get("visual_score", 0)
        combined = verification_result.get("combined_score", 0)

        return f"""
Audio Fingerprint Match: {audio:.1f}%
Visual Fingerprint Match: {visual:.1f}%
Combined Confidence Score: {combined:.1f}%

The content has been analyzed using forensic fingerprinting technology and
positively matched to the authorized broadcast of the copyrighted work.
Multiple fingerprint vectors (audio and visual) confirm the presence of the infringing content.
"""

    def _get_recipient_email(self, platform: str, rights_holder: RightsHolderInfo) -> str:
        """Get the appropriate abuse team email for a platform."""
        platform_emails = {
            "youtube": "copyright@youtube.com",
            "telegram": "abuse@telegram.org",
            "discord": "abuse@discordapp.com",
            "reddit": "dmca-notice@reddit.com",
            "twitter": "legal@twitter.com",
            "cloudflare": "abuse@cloudflare.com",
        }

        # Default to rights holder email if platform not found
        return platform_emails.get(platform, rights_holder.legal_email)
