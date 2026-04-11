"""Tests for the authentication helpers."""

from __future__ import annotations

import pytest

from apex_mcp_server.auth import (
    StaticBearerTokenVerifier,
    build_auth_provider,
)
from apex_mcp_server.config import Settings


@pytest.mark.asyncio
async def test_static_bearer_token_verifier_accepts_matching_token() -> None:
    """Ensure the configured bearer token is accepted.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If a matching token is rejected.
    """

    verifier = StaticBearerTokenVerifier(api_token="demo-token")

    token = await verifier.verify_token("demo-token")

    assert token is not None
    assert token.client_id == "static-bearer"
    assert token.claims == {"sub": "private-profile", "auth_type": "bearer"}


@pytest.mark.asyncio
async def test_static_bearer_token_verifier_rejects_mismatched_token() -> None:
    """Ensure the verifier rejects the wrong bearer token.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If a mismatched token is accepted.
    """

    verifier = StaticBearerTokenVerifier(api_token="demo-token")

    token = await verifier.verify_token("wrong-token")

    assert token is None


def test_build_auth_provider_returns_none_for_no_auth(tmp_path) -> None:
    """Ensure open local mode does not attach an auth provider.

    Parameters:
        tmp_path: Temporary directory fixture used for settings.

    Returns:
        None.

    Raises:
        AssertionError: If no-auth mode returns a provider.
    """

    settings = Settings(
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

    assert build_auth_provider(settings) is None


def test_build_auth_provider_returns_bearer_verifier(tmp_path) -> None:
    """Ensure bearer mode still returns the existing static verifier.

    Parameters:
        tmp_path: Temporary directory fixture used for settings.

    Returns:
        None.

    Raises:
        AssertionError: If bearer mode stops using the static verifier.
    """

    settings = Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="bearer",
        api_token="demo-token",
        public_base_url=None,
        workos_authkit_domain=None,
        profile_storage_backend="file",
        profiles_dir=tmp_path / "profiles",
        blob_prefix="profiles",
        blob_read_write_token=None,
    )

    assert isinstance(build_auth_provider(settings), StaticBearerTokenVerifier)


def test_build_auth_provider_uses_authkit_provider(monkeypatch, tmp_path) -> None:
    """Ensure OAuth mode passes the expected values to AuthKitProvider.

    Parameters:
        monkeypatch: Pytest fixture for patching the provider constructor.
        tmp_path: Temporary directory fixture used for settings.

    Returns:
        None.

    Raises:
        AssertionError: If the AuthKit provider is built with wrong arguments.
    """

    recorded: dict[str, str] = {}

    class FakeAuthKitProvider:
        """Capture AuthKit constructor arguments for test assertions."""

        def __init__(self, *, authkit_domain: str, base_url: str) -> None:
            """Record the constructor values used by build_auth_provider."""

            recorded["authkit_domain"] = authkit_domain
            recorded["base_url"] = base_url

    monkeypatch.setattr("apex_mcp_server.auth.AuthKitProvider", FakeAuthKitProvider)

    settings = Settings(
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

    provider = build_auth_provider(settings)

    assert isinstance(provider, FakeAuthKitProvider)
    assert recorded == {
        "authkit_domain": "https://demo.authkit.app",
        "base_url": "https://example.com",
    }
