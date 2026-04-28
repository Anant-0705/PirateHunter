from __future__ import annotations

import asyncio

from piratehunt.dmca.worker import run_dmca_worker


def main() -> None:
    """Run the Phase 5 DMCA worker."""
    asyncio.run(run_dmca_worker())


if __name__ == "__main__":
    main()
