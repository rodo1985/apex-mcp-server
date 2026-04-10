"""Repository-root ASGI entrypoint for Vercel and local `uvicorn` runs.

Vercel imports this module directly from the repository root. We add `src/` to
`sys.path` explicitly so the package layout stays conventional for contributors
while the platform can still import the application without an editable install.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apex_mcp_server.asgi import app  # noqa: E402

__all__ = ["app"]
