"""Authentication helpers for the FastMCP profile pilot."""

from __future__ import annotations

import secrets

from fastmcp.server.auth import AccessToken, AuthProvider, TokenVerifier
from fastmcp.server.auth.providers.workos import AuthKitProvider

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
        AuthProvider | None: A shared bearer-token verifier, an AuthKit-backed
            OAuth provider, or `None` when authentication is disabled.

    Raises:
        ValueError: Propagated if FastMCP rejects the supplied auth settings.

    Example:
        >>> provider = build_auth_provider(Settings.from_env())
        >>> provider is None or provider.__class__.__name__.endswith("Verifier")
        True
    """

    if settings.auth_mode == "none":
        return None

    if settings.auth_mode == "bearer":
        return StaticBearerTokenVerifier(api_token=settings.api_token or "")

    return build_workos_auth_provider(settings)


def build_workos_auth_provider(settings: Settings) -> AuthProvider:
    """Create the WorkOS AuthKit provider for Claude-compatible OAuth.

    Parameters:
        settings: Normalized runtime settings with OAuth configuration.

    Returns:
        AuthProvider: The FastMCP AuthKit provider for remote OAuth.

    Raises:
        ValueError: Propagated if FastMCP rejects provider construction.

    Example:
        >>> settings = Settings(
        ...     app_name="demo",
        ...     version="0.1.0",
        ...     auth_mode="oauth",
        ...     api_token=None,
        ...     public_base_url="https://example.com",
        ...     workos_authkit_domain="https://example.authkit.app",
        ...     profile_storage_backend="file",
        ...     profiles_dir=__import__("pathlib").Path("."),
        ...     blob_prefix="profiles",
        ...     blob_read_write_token=None,
        ... )
        >>> provider = build_workos_auth_provider(settings)
        >>> provider is not None
        True
    """

    # AuthKit supports the remote MCP OAuth shape Claude expects, so we keep
    # the integration tiny and avoid proxy storage infrastructure.
    return AuthKitProvider(
        authkit_domain=settings.workos_authkit_domain or "",
        base_url=settings.public_base_url or "",
    )
