from __future__ import annotations

import hashlib
import logging
import subprocess

from piratehunt.fingerprint.types import AudioFingerprint

logger = logging.getLogger(__name__)


def fingerprint_audio_chunk(
    pcm_bytes: bytes, sample_rate: int = 44100, source_id: str = "unknown"
) -> AudioFingerprint:
    """
    Generate Chromaprint fingerprint from raw PCM audio bytes.

    Uses the system chromaprint utility via subprocess, or falls back to a
    hash-based fingerprint if the utility is unavailable.

    Args:
        pcm_bytes: Raw PCM audio bytes (16-bit signed, little-endian)
        sample_rate: Sample rate in Hz (default 44100)
        source_id: Identifier for the media source

    Returns:
        AudioFingerprint model with fingerprint hash and metadata
    """
    duration_s = len(pcm_bytes) / (sample_rate * 2)  # 16-bit = 2 bytes per sample

    try:
        # Try to use system chromaprint utility
        fingerprint_hash = _chromaprint_from_cli(pcm_bytes, sample_rate)
    except Exception as e:
        logger.debug(f"Could not use system chromaprint: {e}. Using hash fallback.")
        # Fallback: use SHA256 hash as fingerprint
        fingerprint_hash = hashlib.sha256(pcm_bytes).hexdigest()

    fp = AudioFingerprint(
        fingerprint_hash=fingerprint_hash,
        duration_s=duration_s,
        source_id=source_id,
    )
    logger.debug(
        f"Generated audio fingerprint: hash={fingerprint_hash[:32]}..., "
        f"duration={duration_s:.2f}s, source={source_id}"
    )
    return fp


def _chromaprint_from_cli(pcm_bytes: bytes, sample_rate: int = 44100) -> str:
    """
    Generate Chromaprint fingerprint using the system chromaprint utility.

    Args:
        pcm_bytes: Raw PCM audio bytes
        sample_rate: Sample rate in Hz

    Returns:
        Chromaprint fingerprint hash string

    Raises:
        Exception: If chromaprint CLI is not available or fails
    """
    try:
        process = subprocess.Popen(
            ["fpcalc", "-raw", "-", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(input=pcm_bytes, timeout=10)

        if process.returncode != 0:
            raise RuntimeError(f"fpcalc failed: {stderr.decode()}")

        # Parse output format: DURATION=<int> FINGERPRINT=<hash>
        output = stdout.decode().strip()
        for line in output.split("\n"):
            if line.startswith("FINGERPRINT="):
                return line.split("=", 1)[1]

        raise ValueError(f"No FINGERPRINT in fpcalc output: {output}")

    except FileNotFoundError as err:
        raise RuntimeError(
            "fpcalc (chromaprint CLI) not found. Install chromaprint system package."
        ) from err
