"""Top-level package for the FastMCP profile pilot.

This module intentionally avoids importing the ASGI app at import time so
configuration only happens when the entrypoint explicitly asks for it.
"""

from apex_mcp_server.server import create_mcp_server

__all__ = ["create_mcp_server"]
