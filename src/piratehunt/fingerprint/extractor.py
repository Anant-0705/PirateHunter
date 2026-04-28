from __future__ import annotations

import json
import logging
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Iterator

from PIL import Image

logger = logging.getLogger(__name__)


def extract_audio_and_keyframes(
    source: str | Path,
    window_seconds: int = 5,
    keyframe_interval: int = 2,
) -> Iterator[tuple[bytes, list[Image.Image]]]:
    """
    Extract rolling audio chunks and keyframes from a media file or stream URL.

    Uses ffmpeg to:
    - Extract rolling audio chunks of `window_seconds` length as raw PCM
    - Extract keyframes every `keyframe_interval` seconds as PIL Images

    Args:
        source: Local file path or HLS/RTMP stream URL
        window_seconds: Length of rolling audio windows in seconds
        keyframe_interval: Interval between keyframes in seconds

    Yields:
        Tuples of (audio_pcm_bytes, list_of_keyframe_images) per window
    """
    source_str = str(source)
    logger.info(
        f"Starting extraction from {source_str}: window={window_seconds}s, "
        f"keyframe_interval={keyframe_interval}s"
    )

    # Get duration and basic info
    try:
        probe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=duration",
            "-of",
            "json",
            source_str,
        ]
        probe_result = subprocess.run(
            probe_cmd, capture_output=True, text=True, timeout=10
        )
        probe_data = json.loads(probe_result.stdout)
        duration_s = float(probe_data["streams"][0]["duration"])
        logger.debug(f"Media duration: {duration_s:.2f}s")
    except Exception as e:
        logger.warning(f"Could not probe duration: {e}. Extracting until stream ends.")
        duration_s = float("inf")

    # Extract audio and keyframes using ffmpeg
    # Strategy: read video/audio streams concurrently and emit windows
    audio_sample_rate = 44100
    audio_channels = 1

    ffmpeg_cmd = [
        "ffmpeg",
        "-i",
        source_str,
        # Audio stream: PCM 16-bit mono at 44.1kHz
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(audio_sample_rate),
        "-ac",
        str(audio_channels),
        "pipe:1",
    ]

    try:
        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=4096,
        )

        # Calculate bytes per sample and per window
        bytes_per_sample = audio_channels * 2  # 16-bit = 2 bytes
        bytes_per_second = audio_sample_rate * bytes_per_sample
        window_size_bytes = window_seconds * bytes_per_second

        # Read audio in chunks
        audio_buffer = BytesIO()
        bytes_read = 0

        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break

            audio_buffer.write(chunk)
            bytes_read += len(chunk)

            # Emit window every window_size_bytes
            if audio_buffer.tell() >= window_size_bytes:
                audio_buffer.seek(0)
                window_audio = audio_buffer.read(int(window_size_bytes))

                # Extract keyframes for this window
                window_duration = window_seconds
                keyframes = _extract_keyframes_ffmpeg(
                    source_str, keyframe_interval, window_duration, bytes_read
                )

                yield (window_audio, keyframes)

                # Keep remaining audio for next window
                remaining = audio_buffer.read()
                audio_buffer = BytesIO()
                audio_buffer.write(remaining)

        # Emit final window if any audio remains
        if audio_buffer.tell() > 0:
            audio_buffer.seek(0)
            final_audio = audio_buffer.read()
            if final_audio:
                keyframes = _extract_keyframes_ffmpeg(
                    source_str, keyframe_interval, window_seconds, bytes_read
                )
                yield (final_audio, keyframes)

        process.wait(timeout=5)
        logger.info("Extraction completed successfully")

    except subprocess.TimeoutExpired:
        process.kill()
        logger.error("ffmpeg process timed out")
        raise
    except Exception as e:
        logger.error(f"Error during extraction: {e}")
        raise


def _extract_keyframes_ffmpeg(
    source: str, interval_seconds: int, duration_seconds: float, offset_bytes: int
) -> list[Image.Image]:
    """
    Extract keyframes from a media file using ffmpeg.

    Args:
        source: Media file path or URL
        interval_seconds: Extract keyframes at this interval
        duration_seconds: Duration window to extract from
        offset_bytes: Byte offset (used for logging/debugging)

    Returns:
        List of PIL Image objects
    """
    images = []

    try:
        # Use ffmpeg to extract keyframes as PNG
        ffmpeg_cmd = [
            "ffmpeg",
            "-i",
            source,
            "-vf",
            f"fps=1/{interval_seconds}",
            "-f",
            "image2pipe",
            "-c:v",
            "png",
            "pipe:1",
        ]

        process = subprocess.Popen(
            ffmpeg_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=4096,
        )

        # Read PNG images from stdout
        while True:
            # PNG magic bytes + minimal header to detect frame
            chunk = process.stdout.read(8)
            if not chunk or len(chunk) < 8:
                break

            # Check for PNG magic bytes
            if chunk[:4] != b"\x89PNG":
                continue

            # Read PNG file size (not standard, use frame detection)
            frame_data = chunk
            # Read until we have a complete PNG (simple heuristic)
            while True:
                next_bytes = process.stdout.read(4096)
                if not next_bytes:
                    break
                frame_data += next_bytes
                # Check for next PNG signature or EOF
                if b"\x89PNG" in next_bytes[4:]:
                    break

            try:
                img = Image.open(BytesIO(frame_data))
                img = img.convert("RGB")
                images.append(img)
                logger.debug(f"Extracted keyframe: {img.size}")
            except Exception as e:
                logger.debug(f"Failed to parse image frame: {e}")
                continue

        process.wait(timeout=5)

    except Exception as e:
        logger.warning(f"Could not extract keyframes: {e}")

    return images
