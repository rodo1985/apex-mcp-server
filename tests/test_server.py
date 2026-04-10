"""In-process MCP tests for the profile pilot server."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastmcp import Client

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
        public_base_url=None,
        github_client_id=None,
        github_client_secret=None,
        redis_url=None,
        profile_storage_backend="file",
        profiles_dir=tmp_path / "profiles",
        blob_prefix="profiles",
        blob_read_write_token=None,
        jwt_signing_key=None,
    )


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
