"""Tests for the small Strava OAuth ASGI helper routes."""

from __future__ import annotations

import httpx
import pytest
from starlette.applications import Starlette

from apex_mcp_server.config import Settings
from apex_mcp_server.strava_oauth import mount_strava_oauth_routes


class RouteTokenStore:
    """Tiny store double used by route tests.

    Parameters:
        None.

    Returns:
        RouteTokenStore: Object with the token method required by the route
            callback.
    """

    async def get_external_service_token(
        self,
        subject: str,
        service: str,
    ) -> dict[str, object] | None:
        """Return no saved token for the route status test.

        Parameters:
            subject: Token owner.
            service: External service name.

        Returns:
            dict[str, object] | None: Always `None` for this tiny fake.
        """

        return None

    async def save_external_service_token(
        self,
        subject: str,
        service: str,
        access_token: str | None,
        refresh_token: str,
        expires_at: int | None,
        raw_payload: dict[str, object],
    ) -> dict[str, object]:
        """Return a token row shape without touching a database.

        Parameters:
            subject: Token owner.
            service: External service name.
            access_token: Short-lived access token.
            refresh_token: Latest refresh token.
            expires_at: Optional Unix expiry timestamp.
            raw_payload: Safe token metadata.

        Returns:
            dict[str, object]: Saved token row payload.
        """

        return {
            "subject": subject,
            "service": service,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "raw_payload": raw_payload,
        }


def strava_route_settings() -> Settings:
    """Return settings suitable for Strava OAuth route tests.

    Parameters:
        None.

    Returns:
        Settings: Runtime settings with fake Strava credentials.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url="https://apex.example.com",
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
        strava_client_id="client-id",
        strava_client_secret="client-secret",
    )


@pytest.mark.asyncio
async def test_strava_start_route_redirects_to_authorization_url() -> None:
    """Ensure `/auth/strava/start` redirects the browser to Strava.

    Parameters:
        None.

    Returns:
        None.
    """

    app = Starlette()
    mount_strava_oauth_routes(
        app,
        strava_route_settings(),
        RouteTokenStore(),  # type: ignore[arg-type]
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://apex.example.com",
        follow_redirects=False,
    ) as client:
        response = await client.get("/auth/strava/start")

    assert response.status_code == 307
    assert response.headers["location"].startswith(
        "https://www.strava.com/oauth/authorize?"
    )
    assert "scope=read%2Cactivity%3Aread_all" in response.headers["location"]


@pytest.mark.asyncio
async def test_strava_callback_requires_code() -> None:
    """Ensure the callback route explains missing Strava callback codes.

    Parameters:
        None.

    Returns:
        None.
    """

    app = Starlette()
    mount_strava_oauth_routes(
        app,
        strava_route_settings(),
        RouteTokenStore(),  # type: ignore[arg-type]
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://apex.example.com",
    ) as client:
        response = await client.get("/auth/strava/callback")

    assert response.status_code == 400
    assert response.json() == {"detail": "Strava OAuth callback requires a code."}


@pytest.mark.asyncio
async def test_strava_status_route_hides_secret_values() -> None:
    """Ensure the status route returns safe diagnostic fields.

    Parameters:
        None.

    Returns:
        None.
    """

    app = Starlette()
    mount_strava_oauth_routes(
        app,
        strava_route_settings(),
        RouteTokenStore(),  # type: ignore[arg-type]
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="https://apex.example.com",
    ) as client:
        response = await client.get("/auth/strava/status")

    payload = response.json()

    assert response.status_code == 200
    assert payload["client_id"] == "present"
    assert payload["client_secret"] == "present"
    assert payload["stored_token"] == "missing"
    assert "client-secret" not in str(payload)
