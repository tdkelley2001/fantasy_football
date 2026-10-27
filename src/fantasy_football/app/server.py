"""Loopback-only M6.1 development server entry point."""

from __future__ import annotations

import argparse
from collections.abc import Sequence


LOOPBACK_HOST = "127.0.0.1"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local fantasy-football API")
    parser.add_argument("--database", default="outputs/fantasy_football.sqlite3")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535")

    import uvicorn

    from fantasy_football.app.http import create_app

    uvicorn.run(create_app(database_path=args.database), host=LOOPBACK_HOST, port=args.port)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
