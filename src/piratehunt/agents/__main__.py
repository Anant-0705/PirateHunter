from __future__ import annotations

import asyncio

from piratehunt.agents.candidate_consumer import run_candidate_consumer


def main() -> None:
    """Run the Phase 3 candidate handoff consumer."""
    asyncio.run(run_candidate_consumer())


if __name__ == "__main__":
    main()
