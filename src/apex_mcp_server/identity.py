"""Identity resolution helpers for MCP requests."""

from __future__ import annotations

from typing import Any

from fastmcp import Context
from fastmcp.server.auth import AccessToken
from fastmcp.server.dependencies import get_access_token

from apex_mcp_server.config import AuthMode
from apex_mcp_server.models import UserIdentity


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
        UserIdentity: A normalized identity object with a stable Postgres
            subject.

    Raises:
        RuntimeError: If authenticated mode is enabled but no valid subject can
            be derived from the current token.

    Example:
        >>> from types import SimpleNamespace
        >>> ctx = SimpleNamespace(request_id="req-1")
        >>> resolve_identity(ctx, "none").storage_subject()
        'anonymous'
    """

    active_token = token if token is not None else get_access_token()
    if active_token is None:
        if auth_mode == "none":
            # Local development remains intentionally frictionless, so anonymous
            # mode shares one Postgres row across local requests.
            return UserIdentity(
                authenticated=False,
                subject=None,
                login=None,
                request_id=ctx.request_id,
            )

        raise RuntimeError(
            "Authentication is required but no access token is available for this "
            "request."
        )

    claims = dict(active_token.claims or {})
    subject = _first_string(claims, "sub", "username", "preferred_username")
    if subject is None:
        subject = active_token.client_id.strip() or None

    if subject is None:
        raise RuntimeError(
            "The authenticated token did not include a stable subject or client ID."
        )

    # OAuth providers often expose a friendly login through preferred_username,
    # while bearer mode usually only includes the fixed subject claim.
    login = _first_string(claims, "login", "username", "preferred_username")
    return UserIdentity(
        authenticated=True,
        subject=subject,
        login=login,
        request_id=ctx.request_id,
    )


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
