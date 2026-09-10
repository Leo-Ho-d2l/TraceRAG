"""Cross-platform local development entry point.

``uvicorn app.main:app`` imports the application *inside* an already running
event loop, and uvicorn 0.36+ hands ``asyncio.run`` an explicit loop factory
that hardcodes ``ProactorEventLoop`` on Windows. The async psycopg driver
rejects that loop, so the documented non-Docker workflow fails with
``psycopg.InterfaceError``.

Running the server through this module keeps the two in sync:

    python -m app.serve --reload

The equivalent raw uvicorn invocation is:

    uvicorn app.main:app --loop app.core.event_loop:selector_loop_factory
"""

from __future__ import annotations

import argparse

from app.core.config import settings
from app.core.event_loop import configure_event_loop_policy, uvicorn_loop_setting

configure_event_loop_policy()

import uvicorn  # noqa: E402  (import after the loop policy is installed)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TraceRAG API.")
    parser.add_argument("--host", default=settings.app_host)
    parser.add_argument("--port", type=int, default=settings.app_port)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
        loop=uvicorn_loop_setting(),
    )


if __name__ == "__main__":
    main()
