"""Tests for request identity resolution."""

from __future__ import annotations

from types import SimpleNamespace

from fastmcp.server.auth import AccessToken

from apex_mcp_server.identity import resolve_identity, sanitize_identity_key


def test_resolve_identity_in_no_auth_mode_uses_anonymous_profile() -> None:
    """Ensure local development falls back to a stable anonymous profile key.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the anonymous fallback changes unexpectedly.
    """

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-local"),
        auth_mode="none",
        token=None,
    )

    assert identity.authenticated is False
    assert identity.subject is None
    assert identity.user_key == "anonymous"
    assert identity.request_id == "req-local"


def test_resolve_identity_from_bearer_token_claims() -> None:
    """Ensure authenticated requests derive a stable file-safe storage key.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the subject extraction changes unexpectedly.
    """

    token = AccessToken(
        token="demo-token",
        client_id="static-bearer",
        scopes=[],
        claims={"sub": "private-profile"},
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-auth"),
        auth_mode="bearer",
        token=token,
    )

    assert identity.authenticated is True
    assert identity.subject == "private-profile"
    assert identity.login is None
    assert identity.user_key == "private-profile"


def test_resolve_identity_falls_back_to_client_id_when_subject_is_missing() -> None:
    """Ensure simple bearer tokens still resolve identity without extra claims.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the client ID fallback stops working.
    """

    token = AccessToken(
        token="demo-token",
        client_id="static-bearer",
        scopes=[],
        claims={},
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-client-id"),
        auth_mode="bearer",
        token=token,
    )

    assert identity.subject == "static-bearer"
    assert identity.user_key == "static-bearer"


def test_sanitize_identity_key_replaces_unsafe_characters() -> None:
    """Ensure generated storage keys remain safe for file and blob paths.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If unsafe characters are not normalized.
    """

    assert sanitize_identity_key("private:profile/123") == "private-profile-123"
