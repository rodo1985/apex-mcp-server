"""ASGI application factory for local development and Vercel deployment."""

from __future__ import annotations

from fastmcp import FastMCP

from apex_mcp_server.config import Settings
from apex_mcp_server.server import create_mcp_server


def create_asgi_app() -> tuple[FastMCP, object]:
    """Create the FastMCP server and its ASGI transport application.

    Parameters:
        None.

    Returns:
        tuple[FastMCP, object]: The configured FastMCP server and the Starlette
            ASGI app returned by `FastMCP.http_app(...)`.

    Raises:
        SettingsError: Propagated when runtime settings are incomplete.

    Example:
        >>> server, app = create_asgi_app()
        >>> server.name
        'APEX FastMCP Profile Pilot'
    """

    settings = Settings.from_env()
    server = create_mcp_server(settings=settings)
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )
    return server, app


server, app = create_asgi_app()

