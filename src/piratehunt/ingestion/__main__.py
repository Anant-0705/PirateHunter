from __future__ import annotations

import argparse
import asyncio
import logging

from piratehunt.ingestion.worker import run_worker
from piratehunt.verification.worker import run_verification_worker

logger = logging.getLogger(__name__)


def main() -> None:
    """Run a PirateHunt background worker."""
    parser = argparse.ArgumentParser(description="Run PirateHunt background workers")
    parser.add_argument(
        "--worker",
        choices=["ingestion", "candidate", "verification"],
        default="ingestion",
        help="Worker to run",
    )
    args = parser.parse_args()
    if args.worker == "candidate":
        logger.warning("--worker candidate is deprecated; use --worker verification")
        return
    if args.worker == "verification":
        asyncio.run(run_verification_worker())
    else:
        asyncio.run(run_worker())


if __name__ == "__main__":
    main()
