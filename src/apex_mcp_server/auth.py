"""Authentication helpers for the FastMCP profile pilot."""

from __future__ import annotations

from fastmcp.server.auth import AuthProvider
from fastmcp.server.auth.providers.github import GitHubProvider
from key_value.aio.stores.redis import RedisStore

from apex_mcp_server.config import Settings


def build_auth_provider(settings: Settings) -> AuthProvider | None:
    """Create the configured FastMCP authentication provider.

    Parameters:
        settings: Normalized runtime settings.

    Returns:
        AuthProvider | None: A configured GitHub OAuth proxy, or `None` when
            local development runs with authentication disabled.

    Raises:
        ValueError: Propagated if FastMCP rejects the supplied auth settings.

    Example:
        >>> provider = build_auth_provider(Settings.from_env())
        >>> provider is None or provider.__class__.__name__.endswith("Provider")
        True
    """

    if settings.auth_mode == "none":
        return None

    redis_store = RedisStore(
        url=settings.redis_url,
        default_collection="fastmcp-oauth",
    )

    return GitHubProvider(
        client_id=settings.github_client_id or "",
        client_secret=settings.github_client_secret or "",
        base_url=settings.public_base_url or "",
        issuer_url=settings.public_base_url or "",
        redirect_path="/auth/callback",
        required_scopes=["user"],
        client_storage=redis_store,
        jwt_signing_key=settings.jwt_signing_key,
        cache_ttl_seconds=300,
    )

