"""In-process and HTTP tests for the profile pilot server."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

from apex_mcp_server.config import Settings
from apex_mcp_server.server import create_mcp_server
from apex_mcp_server.storage import FileProfileStore


@pytest.fixture
def no_auth_settings(tmp_path: Path) -> Settings:
    """Return test settings that keep the pilot in local no-auth mode.

    Parameters:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Settings: A local file-backed configuration for in-process tests.

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
        profile_storage_backend="file",
        profiles_dir=tmp_path / "profiles",
        blob_prefix="profiles",
        blob_read_write_token=None,
    )


@pytest.fixture
def bearer_settings(tmp_path: Path) -> Settings:
    """Return test settings that protect the HTTP server with a bearer token.

    Parameters:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Settings: A file-backed configuration that requires `MCP_API_TOKEN`.

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
        profile_storage_backend="file",
        profiles_dir=tmp_path / "profiles",
        blob_prefix="profiles",
        blob_read_write_token=None,
    )


@pytest.fixture
def oauth_settings(tmp_path: Path) -> Settings:
    """Return test settings that enable the OAuth production mode.

    Parameters:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Settings: File-backed OAuth settings for construction tests.

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
        profile_storage_backend="file",
        profiles_dir=tmp_path / "profiles",
        blob_prefix="profiles",
        blob_read_write_token=None,
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
        """Return a sentinel provider so server construction stays offline."""

        assert settings is oauth_settings
        return sentinel

    monkeypatch.setattr(
        "apex_mcp_server.server.build_auth_provider",
        fake_build_auth_provider,
    )

    server = create_mcp_server(
        settings=oauth_settings,
        store=FileProfileStore(oauth_settings.profiles_dir),
    )

    assert server.name == "APEX FastMCP Profile Pilot"


@pytest.mark.asyncio
async def test_server_profile_tools_resource_and_prompt(
    no_auth_settings: Settings,
) -> None:
    """Exercise the pilot end-to-end using FastMCP's in-process client.

    Parameters:
        no_auth_settings: Local file-backed test settings.

    Returns:
        None.

    Raises:
        AssertionError: If any MCP component returns an unexpected result.
    """

    store = FileProfileStore(no_auth_settings.profiles_dir)
    server = create_mcp_server(settings=no_auth_settings, store=store)

    async with Client(server) as client:
        initial_profile = await client.call_tool("get_profile")
        save_result = await client.call_tool(
            "set_profile",
            {"profile_markdown": "# Runner Persona\nWarm and practical."},
        )
        updated_profile = await client.call_tool("get_profile")
        whoami_result = await client.call_tool("whoami")
        resource_result = await client.read_resource("profile://me")
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Write a short training reminder."},
        )

    assert initial_profile.data == ""
    assert save_result.data == {
        "saved": True,
        "pathname": str(no_auth_settings.profiles_dir / "anonymous.md"),
        "bytes": len(b"# Runner Persona\nWarm and practical."),
    }
    assert updated_profile.data == "# Runner Persona\nWarm and practical."
    assert whoami_result.data == {
        "authenticated": False,
        "subject": None,
        "login": None,
        "request_id": whoami_result.data["request_id"],
    }
    assert resource_result[0].text == "# Runner Persona\nWarm and practical."
    assert (
        "Write a short training reminder."
        in prompt_result.messages[0].content.text
    )
    assert (
        "# Runner Persona\nWarm and practical."
        in prompt_result.messages[0].content.text
    )
    assert prompt_result.meta == {"has_profile": True}


@pytest.mark.asyncio
async def test_prompt_reports_missing_profile(no_auth_settings: Settings) -> None:
    """Ensure the prompt includes the empty-profile fallback text.

    Parameters:
        no_auth_settings: Local file-backed test settings.

    Returns:
        None.

    Raises:
        AssertionError: If the prompt omits the fallback text.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=FileProfileStore(no_auth_settings.profiles_dir),
    )

    async with Client(server) as client:
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Introduce yourself."},
        )

    assert (
        "No profile is saved yet for this caller."
        in prompt_result.messages[0].content.text
    )
    assert prompt_result.meta == {"has_profile": False}


@pytest.mark.asyncio
async def test_bearer_token_protects_http_endpoint_and_allows_authenticated_calls(
    bearer_settings: Settings,
) -> None:
    """Ensure the HTTP endpoint rejects anonymous requests and accepts a token.

    Parameters:
        bearer_settings: Settings fixture that enables bearer-token auth.

    Returns:
        None.

    Raises:
        AssertionError: If HTTP authentication does not behave as expected.
    """

    store = FileProfileStore(bearer_settings.profiles_dir)
    server = create_mcp_server(settings=bearer_settings, store=store)
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )
    client_factory = make_httpx_client_factory(app)

    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as raw_client:
            unauthorized = await raw_client.post("/mcp", json=initialize_payload())

        assert unauthorized.status_code == 401

        transport = StreamableHttpTransport(
            url="http://testserver/mcp",
            auth=bearer_settings.api_token,
            httpx_client_factory=client_factory,
        )

        async with Client(transport) as client:
            initial_profile = await client.call_tool("get_profile")
            save_result = await client.call_tool(
                "set_profile",
                {"profile_markdown": "# Private Persona\nSecure and simple."},
            )
            updated_profile = await client.call_tool("get_profile")
            whoami_result = await client.call_tool("whoami")

    assert initial_profile.data == ""
    assert save_result.data == {
        "saved": True,
        "pathname": str(bearer_settings.profiles_dir / "private-profile.md"),
        "bytes": len(b"# Private Persona\nSecure and simple."),
    }
    assert updated_profile.data == "# Private Persona\nSecure and simple."
    assert whoami_result.data == {
        "authenticated": True,
        "subject": "private-profile",
        "login": None,
        "request_id": whoami_result.data["request_id"],
    }
