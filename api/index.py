"""Vercel Python Function entrypoint.

Vercel's Python runtime resolves files under `api/` as serverless functions.
This module mirrors the repository-root `index.py` entrypoint so the same app
can run both locally and on Vercel.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apex_mcp_server.asgi import app  # noqa: E402

__all__ = ["app"]

