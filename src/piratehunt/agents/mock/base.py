from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import aiofiles

from piratehunt.agents.base import DiscoveryAgent
from piratehunt.agents.types import CandidateStream, DiscoveryQuery


class FixtureDiscoveryAgent(DiscoveryAgent):
    """Base implementation for fixture-backed mock discovery agents."""

    source_platform: str
    fixture_name: str
    default_latency_range: tuple[float, float] = (0.5, 2.0)

    def __init__(
        self,
        *,
        fixture_path: Path | None = None,
        latency_range: tuple[float, float] | None = None,
    ) -> None:
        super().__init__()
        default_path = (
            Path(__file__).resolve().parents[4] / "tests" / "fixtures" / self.fixture_name
        )
        self.fixture_path = fixture_path or default_path
        self.latency_range = latency_range or self.default_latency_range

    async def _discover(self, query: DiscoveryQuery) -> AsyncIterator[CandidateStream]:
        if not query.keywords:
            return

        entries = await self._load_entries()
        normalized_keywords = [keyword.casefold() for keyword in query.keywords]
        for entry in entries:
            if not self._matches_keywords(entry, normalized_keywords):
                continue
            await asyncio.sleep(random.uniform(*self.latency_range))
            yield CandidateStream(
                match_id=query.match_id,
                source_platform=self.source_platform,
                source_url=str(entry["source_url"]),
                discovered_by_agent=self.name,
                metadata={
                    key: value
                    for key, value in entry.items()
                    if key not in {"source_url", "confidence_hint"}
                },
                confidence_hint=float(entry.get("confidence_hint", 0.5)),
            )

    async def _load_entries(self) -> list[dict[str, Any]]:
        async with aiofiles.open(self.fixture_path, encoding="utf-8") as file:
            raw = await file.read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            import yaml

            data = yaml.safe_load(raw)
        if not isinstance(data, list):
            msg = f"{self.fixture_path} must contain a list of candidate entries"
            raise ValueError(msg)
        return [dict(item) for item in data]

    def _matches_keywords(self, entry: dict[str, Any], normalized_keywords: list[str]) -> bool:
        text = " ".join(
            str(value)
            for key, value in entry.items()
            if key in {"title", "name", "description", "keywords", "language"}
        ).casefold()
        return any(keyword in text for keyword in normalized_keywords)
