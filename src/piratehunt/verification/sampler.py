from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from piratehunt.verification.types import SampledClip

logger = logging.getLogger(__name__)


class SamplingError(RuntimeError):
    """Raised when all sampling strategies fail."""


async def sample_clip(
    url: str,
    duration_seconds: int = 12,
    work_dir: Path | None = None,
) -> SampledClip:
    """Sample a short clip with yt-dlp, Playwright, then direct ffmpeg fallback."""
    work_dir = work_dir or Path(".samples")
    work_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for strategy in (_sample_with_ytdlp, _sample_with_playwright, _sample_with_direct_ffmpeg):
        try:
            clip = await strategy(url, duration_seconds, work_dir)
            logger.info("Sampled %s with %s", url, clip.sampler_used)
            return clip
        except Exception as exc:
            errors.append(f"{strategy.__name__}: {exc}")
            logger.warning("Sampling strategy %s failed for %s: %s", strategy.__name__, url, exc)
    raise SamplingError("; ".join(errors))


async def _sample_with_ytdlp(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
    def run() -> SampledClip:
        import yt_dlp

        output = work_dir / "yt_dlp_sample.%(ext)s"
        options = {
            "outtmpl": str(output),
            "format": "best[ext=mp4]/best",
            "quiet": True,
            "noplaylist": True,
            "download_sections": [f"*00:00:00-00:00:{duration_seconds:02d}"],
        }
        with yt_dlp.YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
        downloaded = _find_newest_video(work_dir)
        if downloaded is None:
            msg = "yt-dlp did not create a media file"
            raise SamplingError(msg)
        clipped = awaitable_run_ffmpeg_trim(
            downloaded, work_dir / "yt_dlp_clip.mp4", duration_seconds
        )
        source_format = str(info.get("ext") or downloaded.suffix.lstrip(".") or "unknown")
        return SampledClip(
            path=clipped,
            duration=float(min(duration_seconds, info.get("duration") or duration_seconds)),
            source_format=source_format,
            sampler_used="yt-dlp",
        )

    return await asyncio.to_thread(run)


async def _sample_with_playwright(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        raise SamplingError("playwright is not installed") from exc

    media_url: str | None = None
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()

        async def inspect_response(response) -> None:
            nonlocal media_url
            response_url = response.url
            if any(token in response_url for token in (".m3u8", ".mp4", ".ts")):
                media_url = response_url

        page.on("response", inspect_response)
        await page.goto(url, wait_until="networkidle", timeout=15000)
        if media_url is None:
            media_url = await page.eval_on_selector("video", "node => node.currentSrc || node.src")
        await browser.close()

    if not media_url:
        msg = "no video element or media URL found"
        raise SamplingError(msg)
    path = await asyncio.to_thread(
        _run_ffmpeg_trim, media_url, work_dir / "playwright_clip.mp4", duration_seconds
    )
    return SampledClip(
        path=path,
        duration=float(duration_seconds),
        source_format=Path(urlparse(media_url).path).suffix.lstrip(".") or "stream",
        sampler_used="playwright",
    )


async def _sample_with_direct_ffmpeg(
    url: str, duration_seconds: int, work_dir: Path
) -> SampledClip:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix not in {".mp4", ".m3u8", ".ts", ".mov"} and not Path(url).exists():
        msg = "URL is not a direct media URL"
        raise SamplingError(msg)
    path = await asyncio.to_thread(
        _run_ffmpeg_trim, url, work_dir / "ffmpeg_clip.mp4", duration_seconds
    )
    return SampledClip(
        path=path,
        duration=float(duration_seconds),
        source_format=suffix.lstrip(".") or "file",
        sampler_used="ffmpeg",
    )


def _run_ffmpeg_trim(source: str | Path, destination: Path, duration_seconds: int) -> Path:
    if shutil.which("ffmpeg") is None:
        if Path(source).exists():
            shutil.copyfile(source, destination)
            return destination
        msg = "ffmpeg not found"
        raise SamplingError(msg)
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-t",
        str(duration_seconds),
        "-c",
        "copy",
        str(destination),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=duration_seconds + 20)
    if result.returncode != 0:
        msg = result.stderr.strip() or "ffmpeg failed"
        raise SamplingError(msg)
    return destination


def awaitable_run_ffmpeg_trim(source: Path, destination: Path, duration_seconds: int) -> Path:
    """Sync helper used inside a thread by yt-dlp strategy."""
    return _run_ffmpeg_trim(source, destination, duration_seconds)


def _find_newest_video(work_dir: Path) -> Path | None:
    candidates = [
        path
        for path in work_dir.iterdir()
        if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".ts"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
