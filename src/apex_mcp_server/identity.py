"""Identity resolution helpers for MCP requests."""

from __future__ import annotations

import re
from typing import Any

from fastmcp import Context
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from apex_mcp_server.config import AuthMode
from apex_mcp_server.models import UserIdentity

_SAFE_KEY_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


def resolve_identity(
    ctx: Context,
    auth_mode: AuthMode,
    token: AccessToken | None = None,
) -> UserIdentity:
    """Resolve a stable caller identity for the current MCP request.

    Parameters:
        ctx: The current FastMCP request context.
        auth_mode: Active authentication mode for the server.
        token: Optional explicit access token, mainly useful in tests.

    Returns:
        UserIdentity: A normalized identity object with a stable `user_key`.

    Raises:
        RuntimeError: If authenticated mode is enabled but no valid subject claim
            is available.

    Example:
        >>> from types import SimpleNamespace
        >>> ctx = SimpleNamespace(request_id="req-1")
        >>> resolve_identity(ctx, "none").user_key
        'anonymous'
    """

    active_token = token if token is not None else get_access_token()
    if active_token is None:
        if auth_mode == "none":
            # The pilot is intentionally usable locally without an auth stack,
            # so all local requests share one anonymous markdown document.
            return UserIdentity(
                authenticated=False,
                subject=None,
                login=None,
                user_key="anonymous",
                request_id=ctx.request_id,
            )

        raise RuntimeError(
            "Authentication is required but no access token is available for this "
            "request."
        )

    claims = _merge_claims(active_token)
    subject = _first_string(claims, "sub", "user_id", "id")
    if subject is None:
        raise RuntimeError(
            "The authenticated token did not include a stable subject claim."
        )

    login = _first_string(claims, "login", "preferred_username", "username")
    return UserIdentity(
        authenticated=True,
        subject=subject,
        login=login,
        user_key=f"github-{sanitize_identity_key(subject)}",
        request_id=ctx.request_id,
    )


def sanitize_identity_key(value: str) -> str:
    """Normalize an identity fragment so it is safe for file and blob paths.

    Parameters:
        value: Raw identity fragment such as a token subject.

    Returns:
        str: A filesystem-safe identifier.

    Raises:
        RuntimeError: If sanitization would result in an empty identifier.

    Example:
        >>> sanitize_identity_key("user:123")
        'user-123'
    """

    cleaned = _SAFE_KEY_PATTERN.sub("-", value).strip("-")
    if not cleaned:
        raise RuntimeError("Could not derive a safe storage key from the subject.")
    return cleaned


def _merge_claims(token: AccessToken) -> dict[str, Any]:
    """Combine direct and upstream OAuth claims into one lookup dictionary.

    Parameters:
        token: FastMCP access token produced by the auth provider.

    Returns:
        dict[str, Any]: A merged claim dictionary with top-level claims taking
            precedence over nested upstream claims.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> token = AccessToken(
        ...     token="t",
        ...     client_id="c",
        ...     scopes=[],
        ...     claims={"sub": "1"},
        ... )
        >>> _merge_claims(token)
        {'sub': '1'}
    """

    claims = dict(token.claims or {})
    upstream_claims = claims.get("upstream_claims")

    if isinstance(upstream_claims, dict):
        merged_claims = dict(upstream_claims)
        merged_claims.update(claims)
        return merged_claims

    return claims


def _first_string(claims: dict[str, Any], *names: str) -> str | None:
    """Return the first non-empty claim value converted to a string.

    Parameters:
        claims: Claim dictionary to inspect.
        *names: Claim names to try in order.

    Returns:
        str | None: The first non-empty string value, if present.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _first_string({"sub": 123}, "sub")
        '123'
    """

    for name in names:
        value = claims.get(name)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None
