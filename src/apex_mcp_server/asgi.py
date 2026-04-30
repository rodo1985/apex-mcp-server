"""ASGI application factory for local development and Vercel deployment."""

from __future__ import annotations

from fastmcp import FastMCP

from apex_mcp_server.config import Settings
from apex_mcp_server.server import create_mcp_server
from apex_mcp_server.storage import UserStore, build_user_store
from apex_mcp_server.strava_oauth import mount_strava_oauth_routes


def create_asgi_app(
    settings: Settings | None = None,
    store: UserStore | None = None,
) -> tuple[FastMCP, object]:
    """Create the FastMCP server and its ASGI transport application.

    Parameters:
        settings: Optional pre-built runtime settings.
        store: Optional storage backend shared by MCP tools and helper routes.

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

    resolved_settings = settings or Settings.from_env()
    resolved_store = store or build_user_store(resolved_settings)
    server = create_mcp_server(settings=resolved_settings, store=resolved_store)
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )
    mount_strava_oauth_routes(app, resolved_settings, resolved_store)
    return server, app


server, app = create_asgi_app()
