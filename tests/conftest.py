"""Test-wide configuration.

The suite must be deterministic and must never call a paid API. A developer with
`LLM_BACKEND=openai_compatible` in `.env` would otherwise get routing decided by
a remote model: the routing assertions become flaky, every run costs money, and
CI (which has no key) would behave differently from a local run.

Environment variables outrank `.env` in pydantic-settings, and this module is
imported before any application module, so setting it here is enough.

Auto-routing quality is measured by `eval/run_agent.py`, not asserted in tests.
Tests that need the research path request it explicitly with `mode="research"`.
"""

from pathlib import Path
import os
import sys

os.environ["LLM_BACKEND"] = "mock"

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
