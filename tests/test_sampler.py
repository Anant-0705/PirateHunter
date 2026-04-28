from __future__ import annotations

from pathlib import Path

import pytest

from piratehunt.verification import sampler
from piratehunt.verification.sampler import SamplingError
from piratehunt.verification.types import SampledClip


@pytest.mark.asyncio
async def test_sampler_yt_dlp_success_skips_fallbacks(monkeypatch, workspace_tmp):
    calls: list[str] = []

    async def yt_dlp(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
        calls.append("yt")
        path = work_dir / "clip.mp4"
        path.write_bytes(b"video")
        return SampledClip(path=path, duration=12.0, source_format="mp4", sampler_used="yt-dlp")

    async def fallback(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
        calls.append("fallback")
        raise AssertionError("fallback should not be called")

    monkeypatch.setattr(sampler, "_sample_with_ytdlp", yt_dlp)
    monkeypatch.setattr(sampler, "_sample_with_playwright", fallback)
    monkeypatch.setattr(sampler, "_sample_with_direct_ffmpeg", fallback)

    clip = await sampler.sample_clip("https://example.com/video", 12, workspace_tmp)

    assert clip.sampler_used == "yt-dlp"
    assert calls == ["yt"]


@pytest.mark.asyncio
async def test_sampler_falls_back_to_playwright(monkeypatch, workspace_tmp):
    calls: list[str] = []

    async def fail_yt(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
        calls.append("yt")
        raise SamplingError("yt failed")

    async def playwright(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
        calls.append("playwright")
        path = work_dir / "clip.mp4"
        path.write_bytes(b"video")
        return SampledClip(path=path, duration=12.0, source_format="mp4", sampler_used="playwright")

    monkeypatch.setattr(sampler, "_sample_with_ytdlp", fail_yt)
    monkeypatch.setattr(sampler, "_sample_with_playwright", playwright)

    clip = await sampler.sample_clip("https://example.com/video", 12, workspace_tmp)

    assert clip.sampler_used == "playwright"
    assert calls == ["yt", "playwright"]


@pytest.mark.asyncio
async def test_sampler_raises_after_all_strategies_fail(monkeypatch, workspace_tmp):
    async def fail(url: str, duration_seconds: int, work_dir: Path) -> SampledClip:
        raise SamplingError("failed")

    monkeypatch.setattr(sampler, "_sample_with_ytdlp", fail)
    monkeypatch.setattr(sampler, "_sample_with_playwright", fail)
    monkeypatch.setattr(sampler, "_sample_with_direct_ffmpeg", fail)

    with pytest.raises(SamplingError):
        await sampler.sample_clip("https://example.com/video", 12, workspace_tmp)
