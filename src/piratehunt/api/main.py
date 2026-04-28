"""FastAPI application entry point with uvicorn integration."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    """Run the FastAPI server."""
    parser = argparse.ArgumentParser(description="Run the PirateHunt FastAPI server")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to bind to (default: 8000)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="Enable auto-reload on code changes"
    )

    args = parser.parse_args()

    uvicorn.run(
        "piratehunt.api.app:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
