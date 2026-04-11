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


def test_resolve_identity_uses_oauth_subject_and_preferred_username() -> None:
    """Ensure OAuth claims map to stable subject and friendly login fields.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If OAuth claims are not resolved as expected.
    """

    token = AccessToken(
        token="oauth-token",
        client_id="oauth-client",
        scopes=[],
        claims={"sub": "oauth-user-123", "preferred_username": "sergio"},
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-oauth"),
        auth_mode="oauth",
        token=token,
    )

    assert identity.subject == "oauth-user-123"
    assert identity.login == "sergio"
    assert identity.user_key == "oauth-user-123"


def test_resolve_identity_in_oauth_mode_falls_back_to_client_id() -> None:
    """Ensure sparse OAuth tokens still resolve to a stable storage key.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If client ID fallback stops working in OAuth mode.
    """

    token = AccessToken(
        token="oauth-token",
        client_id="oauth-client-id",
        scopes=[],
        claims={},
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-oauth-client"),
        auth_mode="oauth",
        token=token,
    )

    assert identity.subject == "oauth-client-id"
    assert identity.user_key == "oauth-client-id"


def test_sanitize_identity_key_raises_for_empty_result() -> None:
    """Ensure fully unsafe subjects still fail instead of producing bad keys.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        RuntimeError: Expected when sanitization removes all characters.
    """

    try:
        sanitize_identity_key(":::")
    except RuntimeError as exc:
        assert str(exc) == "Could not derive a safe storage key from the subject."
    else:
        raise AssertionError("Expected sanitize_identity_key to reject empty keys.")
