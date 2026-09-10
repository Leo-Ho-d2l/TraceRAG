"""Event-loop compatibility for the async PostgreSQL driver.

psycopg 3 refuses to run in async mode on Windows' default ``ProactorEventLoop``::

    psycopg.InterfaceError: Psycopg cannot use the 'ProactorEventLoop' to run
    in async mode.

Two different mechanisms are needed, because uvicorn 0.36+ stopped using the
event-loop *policy* and instead passes an explicit ``loop_factory`` to
``asyncio.run`` that hardcodes ``ProactorEventLoop`` on win32:

* :func:`configure_event_loop_policy` -- for every entry point that calls
  ``asyncio.run`` itself (``scripts/``, ``eval/``, the Celery worker, pytest's
  ``TestClient``). Importing :mod:`app.db.session` installs it.
* :func:`selector_loop_factory` -- for uvicorn, which must be handed a loop
  factory explicitly via ``--loop app.core.event_loop:selector_loop_factory``
  or the ``loop=`` argument used by :mod:`app.serve`.

Both are no-ops on Linux and macOS, where uvicorn already selects a selector
loop and psycopg has no such restriction.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Coroutine
from typing import Any


def configure_event_loop_policy() -> None:
    """Install a psycopg-compatible policy on Windows (no-op elsewhere)."""
    if sys.platform != "win32":
        return
    selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
    if selector_policy is None:  # pragma: no cover - non-CPython asyncio
        return
    if isinstance(asyncio.get_event_loop_policy(), selector_policy):
        return
    asyncio.set_event_loop_policy(selector_policy())


def selector_loop_factory(*_args: Any, **_kwargs: Any) -> asyncio.AbstractEventLoop:
    """Return a selector event loop.

    uvicorn imports ``--loop`` when it is not one of its built-in names and uses
    the result directly as the loop factory. Extra positional/keyword arguments
    are accepted and ignored so the same callable also works as a policy-style
    setup function.
    """
    return asyncio.SelectorEventLoop()


def uvicorn_loop_setting() -> str:
    """uvicorn ``loop`` value for the current platform.

    On Windows we must force the selector loop. Elsewhere ``auto`` keeps
    uvicorn's normal behaviour (uvloop when installed, selector otherwise).
    """
    if sys.platform == "win32":
        return "app.core.event_loop:selector_loop_factory"
    return "auto"


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
    """``asyncio.run`` for this project's entry points.

    The loop is created by ``asyncio.run`` itself, so the policy has to be
    installed *before* the call -- which is easy to miss when a script only
    imports the database layer lazily inside the coroutine. Those entry points
    failed with ``psycopg.InterfaceError: cannot use the 'ProactorEventLoop'``.
    Using this helper makes it impossible to get the order wrong.
    """
    configure_event_loop_policy()
    return asyncio.run(coro)
