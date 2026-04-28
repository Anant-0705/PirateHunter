from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path
from uuid import uuid4

from PIL import Image

from piratehunt.verification.evidence import EvidenceCollector, LocalEvidenceStorage
from piratehunt.verification.scoring import combined_match_score, verdict_from_scores
from piratehunt.verification.types import GeminiVerificationSignal, SampledClip

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
ENVELOPE = "✉️"


async def run_demo() -> None:
    demo_start = time.monotonic()
    evidence_root = Path("evidence/demo")
    work_dir = evidence_root / "_work"
    work_dir.mkdir(parents=True, exist_ok=True)

    match_id = uuid4()
    candidate_id = uuid4()
    fixture_clip = Path("tests/fixtures/sample.mp4")
    if not fixture_clip.exists():
        fixture_clip = work_dir / "synthetic-sample.mp4"
        fixture_clip.write_bytes(b"synthetic demo clip")

    frame_paths = []
    for idx, color in enumerate(["green", "white", "blue"]):
        frame = work_dir / f"demo-frame-{idx}.png"
        Image.new("RGB", (320, 180), color).save(frame)
        frame_paths.append(frame)

    audio_score = 0.97
    visual_score = 0.94
    combined = combined_match_score(audio_score, visual_score, (0.6, 0.4))
    gemini_signal = GeminiVerificationSignal(
        is_sports_content=True,
        detected_sport="cricket",
        broadcaster_logos_detected=["Mock Sports"],
        confidence=0.92,
        raw_response='{"is_sports_content": true}',
    )
    verdict = verdict_from_scores(
        combined,
        gemini_signal=gemini_signal,
        audio_threshold=0.5,
        visual_threshold=10.0,
        combined_threshold=0.85,
        clean_threshold=0.4,
    )

    from piratehunt.db.models import CandidateStatus, CandidateStream

    candidate = CandidateStream(
        id=candidate_id,
        match_id=match_id,
        source_platform="demo",
        source_url=str(fixture_clip),
        discovered_at=None,
        discovered_by_agent="demo",
        candidate_metadata={"is_pirate": True},
        confidence_hint=0.99,
        status=CandidateStatus.discovered,
    )
    collector = EvidenceCollector(
        storage=LocalEvidenceStorage(evidence_root),
        work_dir=work_dir,
    )
    artifact = await collector.collect(
        candidate,
        SampledClip(path=fixture_clip, duration=12.0, source_format="mp4", sampler_used="demo"),
        frame_paths,
        {"audio_count": 1, "visual_count": 3},
        {"audio_score": audio_score, "visual_score": visual_score, "combined_score": combined},
        gemini_signal,
    )

    detection_elapsed = time.monotonic() - demo_start
    color = RED if verdict == "pirate" else GREEN if verdict == "clean" else YELLOW
    print(f"\n{color}{'='*60}{RESET}")
    print(f"{color}🔍 PIRACY DETECTION BEAT{RESET}")
    print(f"{color}{'='*60}{RESET}")
    print(f"Match ID: {match_id}")
    print(f"Candidate ID: {candidate_id}")
    print(f"Detection latency: {detection_elapsed:.2f}s")
    print(f"Scores: audio={audio_score:.2f} visual={visual_score:.2f} combined={combined:.2f}")
    print(f"Verdict: {color}{verdict.upper()}{RESET}")
    print(f"Evidence artifact: {artifact.artifact_id}")
    print(f"Evidence files: {artifact.storage_uris}")
    if verdict == "pirate":
        print(f"{RED}🚨 PIRATE DETECTED IN {detection_elapsed:.2f} SECONDS{RESET}")

        # Generate DMCA notice if pirate detected
        dmca_start = time.monotonic()
        try:
            from piratehunt.dmca.generator import DMCAGenerator
            from piratehunt.dmca.types import RightsHolderInfo

            print(f"\n{BLUE}{'='*60}{RESET}")
            print(f"{BLUE}📝 DMCA NOTICE GENERATION BEAT{RESET}")
            print(f"{BLUE}{'='*60}{RESET}")

            generator = DMCAGenerator()

            # Create sample rights holder info
            rights_holder = RightsHolderInfo(
                id=str(uuid4()),
                name="Test Sports Rights Holder",
                legal_email="legal@testsports.example.com",
                address="123 Sports Avenue, Demo City, DC 12345",
                authorized_agent="Demo Legal Team",
                default_language="en",
                signature_block="Signed,\nDemo Legal Department\nTest Sports Rights",
            )

            # Prepare verification result data
            verification_data = {
                "audio_score": audio_score,
                "visual_score": visual_score,
                "combined_score": combined,
                "gemini_detected_sport": "cricket",
            }

            # Prepare match data
            match_data = {
                "id": str(match_id),
                "name": "Demo Cricket Match - India vs Australia",
            }

            # Prepare candidate data
            candidate_data = {
                "source_platform": "youtube",
                "source_url": "https://youtube.com/watch?v=demo123456",
                "discovered_at": candidate.discovered_at,
                "candidate_metadata": candidate.candidate_metadata,
            }

            # Generate notice
            draft_notice = await generator.generate(
                verification_data, candidate_data, match_data, rights_holder
            )

            dmca_elapsed = time.monotonic() - dmca_start

            print(f"{BLUE}Platform: {draft_notice.platform}{RESET}")
            print(f"{BLUE}Subject: {draft_notice.subject}{RESET}")
            print(f"{BLUE}Recipient: {draft_notice.recipient_email_or_form_url}{RESET}")
            print(f"{BLUE}Language: {draft_notice.language}{RESET}")
            print(f"{BLUE}Gemini Polish Applied: {draft_notice.gemini_polish_applied}{RESET}")
            print(f"\n{BLUE}Notice Body (first 300 chars):{RESET}")
            print(f"{BLUE}{draft_notice.body[:300]}...{RESET}")
            print(f"\n{BLUE}{ENVELOPE} DMCA NOTICE READY FOR REVIEW{RESET}")
            print(f"{BLUE}Generation time: {dmca_elapsed:.2f}s{RESET}")
            print(f"{BLUE}Total time from candidate to drafted notice: {detection_elapsed + dmca_elapsed:.2f}s{RESET}")

        except Exception as e:
            print(f"{RED}Failed to generate DMCA notice: {e}{RESET}")

    print(f"\n{color}{'='*60}{RESET}")
    print(f"{color}Demo complete{RESET}")
    print(f"{color}{'='*60}{RESET}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the PirateHunt stage demo")
    parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
