"""Tests for request identity resolution."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
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


def test_resolve_identity_from_access_token_claims() -> None:
    """Ensure authenticated requests derive a stable GitHub-based storage key.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the subject or login extraction changes unexpectedly.
    """

    token = AccessToken(
        token="demo-token",
        client_id="client-1",
        scopes=["user"],
        claims={"sub": "12345", "login": "octocat"},
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-auth"),
        auth_mode="github",
        token=token,
    )

    assert identity.authenticated is True
    assert identity.subject == "12345"
    assert identity.login == "octocat"
    assert identity.user_key == "github-12345"


def test_resolve_identity_uses_upstream_claims_when_present() -> None:
    """Ensure OAuth proxy tokens still resolve identity from nested claims.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If nested upstream claims are ignored.
    """

    token = AccessToken(
        token="demo-token",
        client_id="client-1",
        scopes=["user"],
        claims={
            "upstream_claims": {"sub": "999", "login": "pilot-user"},
        },
    )

    identity = resolve_identity(
        ctx=SimpleNamespace(request_id="req-upstream"),
        auth_mode="github",
        token=token,
    )

    assert identity.subject == "999"
    assert identity.login == "pilot-user"
    assert identity.user_key == "github-999"


def test_sanitize_identity_key_replaces_unsafe_characters() -> None:
    """Ensure generated storage keys remain safe for files and blob paths.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If unsafe characters are not normalized.
    """

    assert sanitize_identity_key("github:user/123") == "github-user-123"


def test_resolve_identity_requires_subject_in_authenticated_mode() -> None:
    """Ensure authenticated mode rejects tokens without a stable subject.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the missing-subject case does not raise.
    """

    token = AccessToken(
        token="demo-token",
        client_id="client-1",
        scopes=["user"],
        claims={},
    )

    with pytest.raises(RuntimeError, match="stable subject"):
        resolve_identity(
            ctx=SimpleNamespace(request_id="req-error"),
            auth_mode="github",
            token=token,
        )

