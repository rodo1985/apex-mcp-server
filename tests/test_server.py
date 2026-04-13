"""In-process and HTTP tests for the Postgres-backed profile pilot server."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest
from fastmcp import Client

from apex_mcp_server.config import Settings
from apex_mcp_server.models import ProfileSaveResult, UserData, UserDataSaveResult
from apex_mcp_server.server import create_mcp_server
from apex_mcp_server.storage import UserStore


class InMemoryUserStore(UserStore):
    """Small in-memory store used to test the MCP surface without Postgres.

    Parameters:
        None.

    Returns:
        InMemoryUserStore: Minimal test double that mirrors the Postgres shape.
    """

    def __init__(self) -> None:
        """Initialize the internal dictionaries used by the fake store.

        Parameters:
            None.

        Returns:
            None.
        """

        self.profiles: dict[str, str] = {}
        self.user_data: dict[str, UserData] = {}

    async def get_profile(self, subject: str) -> str:
        """Return the stored profile markdown for a subject."""

        return self.profiles.get(subject, "")

    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Store markdown in memory and return a save summary.

        Parameters:
            subject: Stable subject for the current caller.
            profile_markdown: Markdown profile content.
            login: Unused login value kept for interface parity.

        Returns:
            ProfileSaveResult: Save confirmation matching the production shape.
        """

        del login
        self.profiles[subject] = profile_markdown
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(profile_markdown.encode("utf-8")),
        )

    async def get_user_data(self, subject: str) -> UserData:
        """Return numeric user data or an all-null structure when missing."""

        return self.user_data.get(
            subject,
            UserData(weight_kg=None, height_cm=None, ftp_watts=None),
        )

    async def set_user_data(
        self,
        subject: str,
        data: UserData,
        login: str | None = None,
    ) -> UserDataSaveResult:
        """Store numeric user data in memory and return a save summary.

        Parameters:
            subject: Stable subject for the current caller.
            data: Numeric data to persist.
            login: Unused login value kept for interface parity.

        Returns:
            UserDataSaveResult: Save confirmation matching the production shape.
        """

        del login
        self.user_data[subject] = data
        return UserDataSaveResult(
            saved=True,
            subject=subject,
            weight_kg=data.weight_kg,
            height_cm=data.height_cm,
            ftp_watts=data.ftp_watts,
        )

    async def close(self) -> None:
        """Release fake resources.

        Parameters:
            None.

        Returns:
            None.
        """


@pytest.fixture
def no_auth_settings() -> Settings:
    """Return test settings that keep the pilot in local no-auth mode.

    Parameters:
        None.

    Returns:
        Settings: A local configuration for in-process tests.

    Raises:
        This fixture does not raise errors directly.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


@pytest.fixture
def bearer_settings() -> Settings:
    """Return test settings that protect the HTTP server with a bearer token.

    Parameters:
        None.

    Returns:
        Settings: A configuration that requires `MCP_API_TOKEN`.

    Raises:
        This fixture does not raise errors directly.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="bearer",
        api_token="top-secret-token",
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


@pytest.fixture
def oauth_settings() -> Settings:
    """Return test settings that enable the OAuth production mode.

    Parameters:
        None.

    Returns:
        Settings: OAuth settings for construction tests.

    Raises:
        This fixture does not raise errors directly.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="oauth",
        api_token=None,
        public_base_url="https://example.com",
        workos_authkit_domain="https://demo.authkit.app",
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


def make_httpx_client_factory(app: Any) -> Callable[..., httpx.AsyncClient]:
    """Create an httpx client factory that targets an in-process ASGI app.

    Parameters:
        app: ASGI application returned by `FastMCP.http_app(...)`.

    Returns:
        Callable[..., httpx.AsyncClient]: Factory compatible with FastMCP's
            HTTP transport hooks.

    Raises:
        This helper does not raise errors directly.
    """

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        """Construct an AsyncClient that routes requests into the ASGI app.

        Parameters:
            **kwargs: Client options forwarded by FastMCP's HTTP transport.

        Returns:
            httpx.AsyncClient: A client backed by `httpx.ASGITransport`.

        Raises:
            This helper does not raise errors directly.
        """

        kwargs.setdefault("base_url", "http://testserver")
        kwargs["transport"] = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(**kwargs)

    return factory


def initialize_payload() -> dict[str, object]:
    """Return a minimal MCP initialize request body for HTTP auth tests.

    Parameters:
        None.

    Returns:
        dict[str, object]: JSON-RPC payload accepted by the MCP endpoint.

    Raises:
        This helper does not raise errors directly.
    """

    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest-client", "version": "0.1.0"},
        },
    }


def test_server_can_be_constructed_in_oauth_mode(
    monkeypatch,
    oauth_settings: Settings,
) -> None:
    """Ensure server assembly works when OAuth mode is selected.

    Parameters:
        monkeypatch: Pytest fixture for patching auth provider creation.
        oauth_settings: OAuth settings fixture for server construction.

    Returns:
        None.

    Raises:
        AssertionError: If the server cannot be built with OAuth settings.
    """

    sentinel = object()

    def fake_build_auth_provider(settings: Settings) -> object:
        """Return a sentinel provider so server construction stays offline.

        Parameters:
            settings: Runtime settings passed from the server factory.

        Returns:
            object: Sentinel auth provider used for assertions.
        """

        assert settings is oauth_settings
        return sentinel

    monkeypatch.setattr(
        "apex_mcp_server.server.build_auth_provider",
        fake_build_auth_provider,
    )

    server = create_mcp_server(settings=oauth_settings, store=InMemoryUserStore())

    assert server.name == "APEX FastMCP Profile Pilot"


@pytest.mark.asyncio
async def test_server_profile_tools_resource_prompt_and_user_data(
    no_auth_settings: Settings,
) -> None:
    """Exercise the pilot end-to-end using FastMCP's in-process client.

    Parameters:
        no_auth_settings: Local test settings.

    Returns:
        None.

    Raises:
        AssertionError: If any MCP component returns an unexpected result.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        initial_profile = await client.call_tool("get_profile")
        initial_user_data = await client.call_tool("get_user_data")
        save_profile_result = await client.call_tool(
            "set_profile",
            {"profile_markdown": "# Runner Persona\nWarm and practical."},
        )
        save_user_data_result = await client.call_tool(
            "set_user_data",
            {"weight_kg": 68.5, "height_cm": 174.0, "ftp_watts": 250},
        )
        updated_profile = await client.call_tool("get_profile")
        updated_user_data = await client.call_tool("get_user_data")
        whoami_result = await client.call_tool("whoami")
        resource_result = await client.read_resource("profile://me")
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Write a short training reminder."},
        )

    assert initial_profile.data == ""
    assert initial_user_data.data == {
        "weight_kg": None,
        "height_cm": None,
        "ftp_watts": None,
    }
    assert save_profile_result.data == {
        "saved": True,
        "subject": "anonymous",
        "bytes": len(b"# Runner Persona\nWarm and practical."),
    }
    assert save_user_data_result.data == {
        "saved": True,
        "subject": "anonymous",
        "weight_kg": 68.5,
        "height_cm": 174.0,
        "ftp_watts": 250,
    }
    assert updated_profile.data == "# Runner Persona\nWarm and practical."
    assert updated_user_data.data == {
        "weight_kg": 68.5,
        "height_cm": 174.0,
        "ftp_watts": 250,
    }
    assert whoami_result.data == {
        "authenticated": False,
        "subject": None,
        "login": None,
        "request_id": whoami_result.data["request_id"],
    }
    assert resource_result[0].text == "# Runner Persona\nWarm and practical."
    assert "Write a short training reminder." in prompt_result.messages[0].content.text
    assert (
        "# Runner Persona\nWarm and practical."
        in prompt_result.messages[0].content.text
    )
    assert prompt_result.meta == {"has_profile": True}


@pytest.mark.asyncio
async def test_prompt_reports_missing_profile(no_auth_settings: Settings) -> None:
    """Ensure the prompt includes the empty-profile fallback text.

    Parameters:
        no_auth_settings: Local test settings.

    Returns:
        None.

    Raises:
        AssertionError: If the missing-profile fallback changes unexpectedly.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Draft an intro message."},
        )

    assert "No profile is saved yet for this caller." in prompt_result.messages[
        0
    ].content.text
    assert prompt_result.meta == {"has_profile": False}


@pytest.mark.asyncio
async def test_bearer_http_app_requires_authorization_header(
    bearer_settings: Settings,
) -> None:
    """Ensure the HTTP transport rejects requests without the shared token.

    Parameters:
        bearer_settings: Bearer-protected settings fixture.

    Returns:
        None.

    Raises:
        AssertionError: If unauthorized requests are no longer rejected.
    """

    server = create_mcp_server(
        settings=bearer_settings,
        store=InMemoryUserStore(),
    )
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/mcp", json=initialize_payload())

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_http_transport_accepts_valid_authorization_header(
    bearer_settings: Settings,
) -> None:
    """Ensure the HTTP transport initializes successfully with the token.

    Parameters:
        bearer_settings: Bearer-protected settings fixture.

    Returns:
        None.

    Raises:
        AssertionError: If authorized requests stop working.
    """

    server = create_mcp_server(
        settings=bearer_settings,
        store=InMemoryUserStore(),
    )
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={
                "Authorization": "Bearer top-secret-token",
                "Accept": "application/json, text/event-stream",
            },
    ) as client:
            response = await client.post("/mcp", json=initialize_payload())

    assert response.status_code == 200
    assert "APEX FastMCP Profile Pilot" in response.text
