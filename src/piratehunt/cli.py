"""Command-line interface for PirateHunt."""

from __future__ import annotations

import argparse
import asyncio
import sys


def main() -> None:
    """Main entry point for PirateHunt CLI."""
    parser = argparse.ArgumentParser(
        description="PirateHunt: Real-time piracy detection for sports broadcasts"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # API server command
    api_parser = subparsers.add_parser("api", help="Run the FastAPI server")
    api_parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    api_parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )

    # Worker command
    worker_parser = subparsers.add_parser("worker", help="Run a background worker")
    worker_parser.add_argument(
        "type",
        choices=["dmca"],
        help="Type of worker to run",
    )

    args = parser.parse_args()

    if args.command == "api":
        run_api(args.host, args.port)
    elif args.command == "worker":
        run_worker_by_type(args.type)
    else:
        parser.print_help()
        sys.exit(1)


def run_api(host: str, port: int) -> None:
    """Run the FastAPI server."""
    import uvicorn

    uvicorn.run(
        "piratehunt.api.app:app",
        host=host,
        port=port,
        reload=False,
    )


def run_worker_by_type(worker_type: str) -> None:
    """Run a specific type of worker."""
    if worker_type == "dmca":
        run_dmca_worker()
    else:
        raise ValueError(f"Unknown worker type: {worker_type}")


def run_dmca_worker() -> None:
    """Run the DMCA worker."""
    from piratehunt.dmca.worker import run_dmca_worker as dmca_main

    asyncio.run(dmca_main())


if __name__ == "__main__":
    main()
