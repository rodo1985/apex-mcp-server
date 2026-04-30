"""Small Starlette routes for connecting the singleton Strava account."""

from __future__ import annotations

import httpx
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from apex_mcp_server.config import Settings, SettingsError
from apex_mcp_server.external_services import (
    StravaAPIError,
    build_strava_authorization_url,
    connect_strava_account,
)
from apex_mcp_server.storage import UserStore


def mount_strava_oauth_routes(
    app: object,
    settings: Settings,
    store: UserStore,
) -> None:
    """Attach Strava OAuth helper routes to the ASGI app.

    Parameters:
        app: Starlette-compatible ASGI app returned by FastMCP.
        settings: Runtime settings used to build Strava OAuth URLs.
        store: Shared user store where the callback saves token bundles.

    Returns:
        None.

    Raises:
        AttributeError: If the supplied app is not Starlette-compatible.

    Example:
        >>> # mount_strava_oauth_routes(app, settings, store)
    """

    existing_paths = {
        getattr(route, "path", None) for route in getattr(app, "routes", [])
    }
    routes = app.routes
    if "/auth/strava/start" not in existing_paths:
        routes.append(
            Route(
                "/auth/strava/start",
                _build_start_endpoint(settings),
                methods=["GET"],
            )
        )
    if "/auth/strava/callback" not in existing_paths:
        routes.append(
            Route(
                "/auth/strava/callback",
                _build_callback_endpoint(settings, store),
                methods=["GET"],
            )
        )


def _build_start_endpoint(settings: Settings):
    """Build the `/auth/strava/start` endpoint closure.

    Parameters:
        settings: Runtime settings used to create the Strava authorization URL.

    Returns:
        Callable: Starlette endpoint that redirects to Strava.

    Raises:
        This helper does not raise errors directly.
    """

    async def start_strava_auth(request: Request) -> Response:
        """Redirect the browser to Strava's OAuth consent page.

        Parameters:
            request: Incoming Starlette request.

        Returns:
            Response: Redirect to Strava, or a JSON configuration error.

        Raises:
            This endpoint converts expected errors into HTTP responses.
        """

        state = request.query_params.get("state")
        try:
            url = build_strava_authorization_url(settings, state=state)
        except SettingsError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=500)
        return RedirectResponse(url)

    return start_strava_auth


def _build_callback_endpoint(settings: Settings, store: UserStore):
    """Build the `/auth/strava/callback` endpoint closure.

    Parameters:
        settings: Runtime settings used to exchange the OAuth code.
        store: Shared user store where token bundles are saved.

    Returns:
        Callable: Starlette endpoint that completes Strava OAuth.

    Raises:
        This helper does not raise errors directly.
    """

    async def strava_auth_callback(request: Request) -> Response:
        """Exchange Strava's OAuth code and save the resulting token bundle.

        Parameters:
            request: Incoming callback request from Strava.

        Returns:
            Response: JSON connection summary without token values.

        Raises:
            This endpoint converts expected errors into HTTP responses.
        """

        error = request.query_params.get("error")
        if error:
            return JSONResponse(
                {"detail": f"Strava OAuth was not completed: {error}."},
                status_code=400,
            )

        code = request.query_params.get("code")
        if not code:
            return JSONResponse(
                {"detail": "Strava OAuth callback requires a code."},
                status_code=400,
            )

        try:
            summary = await connect_strava_account(
                settings=settings,
                store=store,
                code=code,
                granted_scope=request.query_params.get("scope"),
            )
        except ValueError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=400)
        except SettingsError as exc:
            return JSONResponse({"detail": str(exc)}, status_code=500)
        except (StravaAPIError, httpx.HTTPError, RuntimeError) as exc:
            return JSONResponse({"detail": str(exc)}, status_code=502)

        return JSONResponse(summary)

    return strava_auth_callback
