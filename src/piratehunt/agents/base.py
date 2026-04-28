from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from datetime import datetime
from functools import wraps
from typing import TypeVar

from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from piratehunt.agents.types import AgentHealth, CandidateStream, DiscoveryQuery

F = TypeVar("F", bound=Callable[..., AsyncIterator[CandidateStream]])


def retry_discovery(func: F) -> F:
    """Retry an async discovery iterator with exponential backoff."""

    @wraps(func)
    async def wrapper(
        self: DiscoveryAgent, query: DiscoveryQuery
    ) -> AsyncIterator[CandidateStream]:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.25, min=0.25, max=2.0),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        ):
            with attempt:
                async for candidate in func(self, query):
                    yield candidate
                return

    return wrapper  # type: ignore[return-value]


class DiscoveryAgent(ABC):
    """Base contract for swappable discovery agents."""

    name: str = "base"

    def __init__(self) -> None:
        self._last_run = datetime.utcnow()
        self._last_error: str | None = None

    @retry_discovery
    async def discover(self, query: DiscoveryQuery) -> AsyncIterator[CandidateStream]:
        """Yield candidates as they are discovered."""
        self._last_run = datetime.utcnow()
        self._last_error = None
        try:
            async for candidate in self._discover(query):
                yield candidate
        except Exception as exc:
            self._last_error = str(exc)
            raise

    @abstractmethod
    async def _discover(self, query: DiscoveryQuery) -> AsyncIterator[CandidateStream]:
        """Implementation hook for platform-specific discovery."""
        if False:
            yield  # pragma: no cover

    async def health_check(self) -> AgentHealth:
        """Return the latest local health state."""
        return AgentHealth(
            healthy=self._last_error is None,
            last_run=self._last_run,
            error=self._last_error,
        )
