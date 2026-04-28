from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker

from piratehunt.agents.base import DiscoveryAgent
from piratehunt.agents.types import AgentHealth, CandidateStream, DiscoveryQuery
from piratehunt.config import settings
from piratehunt.db.engine import async_session_maker
from piratehunt.db.models import AgentRunStatus
from piratehunt.db.repository import (
    complete_agent_run,
    create_agent_run,
    insert_candidate_stream,
)

logger = logging.getLogger(__name__)


class GlobalRateLimiter:
    """Tiny async rate limiter shared across all discovery agents."""

    def __init__(self, rate_per_second: float) -> None:
        self.interval_seconds = 1.0 / max(rate_per_second, 0.1)
        self._lock = asyncio.Lock()
        self._last_emit = 0.0

    async def wait(self) -> None:
        """Wait until another globally rate-limited event may be emitted."""
        async with self._lock:
            now = time.monotonic()
            sleep_for = self.interval_seconds - (now - self._last_emit)
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
            self._last_emit = time.monotonic()


@dataclass
class AgentMetrics:
    """Per-agent discovery metrics."""

    candidates_found: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)

    @property
    def avg_latency(self) -> float:
        """Average candidate latency in seconds."""
        if not self.latencies:
            return 0.0
        return sum(self.latencies) / len(self.latencies)


@dataclass
class DiscoveryRunState:
    """Tracks running asyncio tasks for one discovery run."""

    run_id: uuid.UUID
    tasks: list[asyncio.Task[None]]
    drain_task: asyncio.Task[None]


class AgentOrchestrator:
    """Runs discovery agents in parallel and persists discovered candidates."""

    def __init__(
        self,
        *,
        redis: Redis,
        session_maker: async_sessionmaker = async_session_maker,
        per_agent_budget_per_minute: int | None = None,
        global_rate_per_second: float | None = None,
    ) -> None:
        self.redis = redis
        self.session_maker = session_maker
        self.per_agent_budget_per_minute = (
            per_agent_budget_per_minute or settings.agent_candidate_budget_per_minute
        )
        self.rate_limiter = GlobalRateLimiter(
            global_rate_per_second or settings.discovery_global_rate_per_second
        )
        self.agents: dict[str, DiscoveryAgent] = {}
        self.metrics: dict[str, AgentMetrics] = {}
        self._runs: dict[uuid.UUID, DiscoveryRunState] = {}

    def register(self, agent: DiscoveryAgent) -> None:
        """Register one discovery agent."""
        self.agents[agent.name] = agent
        self.metrics.setdefault(agent.name, AgentMetrics())

    def register_many(self, agents: list[DiscoveryAgent]) -> None:
        """Register multiple discovery agents."""
        for agent in agents:
            self.register(agent)

    async def start_discovery(self, query: DiscoveryQuery) -> uuid.UUID:
        """Start one parallel discovery run and return its run ID."""
        run_id = uuid.uuid4()
        queue: asyncio.Queue[CandidateStream | None] = asyncio.Queue()
        tasks = [
            asyncio.create_task(self._run_agent(agent, query, queue), name=f"discover-{agent.name}")
            for agent in self.agents.values()
        ]
        drain_task = asyncio.create_task(
            self._drain_candidates(run_id, queue, expected_sentinels=len(tasks)),
            name=f"discover-drain-{run_id}",
        )
        self._runs[run_id] = DiscoveryRunState(run_id=run_id, tasks=tasks, drain_task=drain_task)
        return run_id

    async def wait_for_run(self, run_id: uuid.UUID) -> None:
        """Wait for a discovery run to finish."""
        state = self._runs.get(run_id)
        if state is None:
            return
        await asyncio.gather(*state.tasks, return_exceptions=True)
        await state.drain_task

    async def stop(self) -> None:
        """Cancel all running agent tasks cleanly."""
        for state in self._runs.values():
            for task in state.tasks:
                task.cancel()
            state.drain_task.cancel()
        await asyncio.gather(
            *(task for state in self._runs.values() for task in [*state.tasks, state.drain_task]),
            return_exceptions=True,
        )
        self._runs.clear()

    async def health(self) -> dict[str, AgentHealth]:
        """Return health for all registered agents."""
        return {name: await agent.health_check() for name, agent in self.agents.items()}

    async def _run_agent(
        self,
        agent: DiscoveryAgent,
        query: DiscoveryQuery,
        queue: asyncio.Queue[CandidateStream | None],
    ) -> None:
        run_id: uuid.UUID | None = None
        started = time.monotonic()
        candidates_found = 0
        try:
            async with self.session_maker() as session:
                run = await create_agent_run(session, query.match_id, agent.name)
                run_id = run.id

            async for candidate in agent.discover(query):
                if candidates_found >= self.per_agent_budget_per_minute:
                    logger.info("Agent %s hit its per-minute candidate budget", agent.name)
                    break
                await self.rate_limiter.wait()
                await queue.put(candidate)
                candidates_found += 1
                self.metrics[agent.name].candidates_found += 1
                self.metrics[agent.name].latencies.append(time.monotonic() - started)

            if run_id is not None:
                async with self.session_maker() as session:
                    await complete_agent_run(
                        session,
                        run_id,
                        AgentRunStatus.succeeded,
                        candidates_found=candidates_found,
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Discovery agent %s failed", agent.name)
            self.metrics[agent.name].errors += 1
            if run_id is not None:
                async with self.session_maker() as session:
                    await complete_agent_run(
                        session,
                        run_id,
                        AgentRunStatus.failed,
                        candidates_found=candidates_found,
                        error=str(exc),
                    )
        finally:
            logger.info(
                "Agent %s metrics: candidates=%s errors=%s avg_latency=%.3fs",
                agent.name,
                self.metrics[agent.name].candidates_found,
                self.metrics[agent.name].errors,
                self.metrics[agent.name].avg_latency,
            )
            await queue.put(None)

    async def _drain_candidates(
        self,
        run_id: uuid.UUID,
        queue: asyncio.Queue[CandidateStream | None],
        *,
        expected_sentinels: int,
    ) -> None:
        sentinels = 0
        while sentinels < expected_sentinels:
            candidate = await queue.get()
            if candidate is None:
                sentinels += 1
                continue
            await self.redis.xadd(
                settings.redis_candidates_stream,
                {"event": candidate.model_dump_json()},
            )
            async with self.session_maker() as session:
                await insert_candidate_stream(session, candidate)
            logger.debug("Discovery run %s persisted candidate %s", run_id, candidate.source_url)
