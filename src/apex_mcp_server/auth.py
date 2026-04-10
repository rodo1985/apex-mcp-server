"""Authentication helpers for the FastMCP profile pilot."""

from __future__ import annotations

import secrets

from fastmcp.server.auth import AccessToken, AuthProvider, TokenVerifier

from apex_mcp_server.config import Settings

PRIVATE_PROFILE_SUBJECT = "private-profile"


class StaticBearerTokenVerifier(TokenVerifier):
    """Validate a single shared bearer token for the entire MCP server.

    Parameters:
        api_token: Shared token that clients must send as a bearer token.
        subject: Stable subject claim exposed to the rest of the server.

    Returns:
        StaticBearerTokenVerifier: A lightweight token verifier for private
            machine-to-machine access.

    Raises:
        This class does not raise errors directly because settings validation
            happens before it is created.

    Example:
        >>> verifier = StaticBearerTokenVerifier(api_token="demo-token")
        >>> verifier.subject
        'private-profile'
    """

    def __init__(
        self,
        api_token: str,
        subject: str = PRIVATE_PROFILE_SUBJECT,
    ) -> None:
        """Store the shared token and stable identity subject.

        Parameters:
            api_token: Shared token that must match incoming bearer tokens.
            subject: Stable subject claim returned for valid requests.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.
        """

        super().__init__()
        self.api_token = api_token
        self.subject = subject

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify that an incoming bearer token matches the configured secret.

        Parameters:
            token: Raw bearer token extracted from the Authorization header.

        Returns:
            AccessToken | None: A small FastMCP access token object when the
                shared secret matches, otherwise `None`.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> import asyncio
            >>> verifier = StaticBearerTokenVerifier(api_token="demo-token")
            >>> result = asyncio.run(verifier.verify_token("demo-token"))
            >>> result is not None
            True
        """

        if not secrets.compare_digest(token, self.api_token):
            return None

        # The pilot intentionally exposes one protected profile document rather
        # than per-user accounts. A fixed subject keeps storage deterministic.
        return AccessToken(
            token=token,
            client_id="static-bearer",
            scopes=[],
            claims={"sub": self.subject, "auth_type": "bearer"},
        )


def build_auth_provider(settings: Settings) -> AuthProvider | None:
    """Create the configured FastMCP authentication provider.

    Parameters:
        settings: Normalized runtime settings.

    Returns:
        AuthProvider | None: A shared bearer-token verifier, or `None` when
            authentication is disabled.

    Raises:
        ValueError: Propagated if FastMCP rejects the supplied auth settings.

    Example:
        >>> provider = build_auth_provider(Settings.from_env())
        >>> provider is None or provider.__class__.__name__.endswith("Verifier")
        True
    """

    if settings.auth_mode == "none":
        return None

    return StaticBearerTokenVerifier(api_token=settings.api_token or "")
