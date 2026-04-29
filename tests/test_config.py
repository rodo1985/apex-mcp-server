"""Tests for environment-driven settings resolution."""

from __future__ import annotations

from apex_mcp_server.config import Settings, _resolve_auth_mode
from apex_mcp_server.storage import PostgresUserStore, build_user_store


def test_resolve_auth_mode_defaults_to_none_without_token() -> None:
    """Ensure the pilot stays open locally unless a bearer token is configured.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the default auth mode changes unexpectedly.
    """

    auth_mode = _resolve_auth_mode({})  # type: ignore[arg-type]

    assert auth_mode == "none"


def test_resolve_auth_mode_defaults_to_bearer_when_token_exists() -> None:
    """Ensure a configured bearer token automatically enables private mode.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the API token does not switch auth to bearer mode.
    """

    auth_mode = _resolve_auth_mode(  # type: ignore[arg-type]
        {"MCP_API_TOKEN": "demo-token"}
    )

    assert auth_mode == "bearer"


def test_resolve_auth_mode_honors_explicit_oauth_mode() -> None:
    """Ensure explicit OAuth mode wins over auto-detection defaults.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If explicit OAuth mode is ignored.
    """

    auth_mode = _resolve_auth_mode(  # type: ignore[arg-type]
        {"MCP_AUTH_MODE": "oauth"}
    )

    assert auth_mode == "oauth"


def test_settings_require_database_url(monkeypatch) -> None:
    """Ensure the Postgres baseline fails fast without a database URL.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If settings load without a database URL.
    """

    monkeypatch.delenv("DATABASE_URL", raising=False)

    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert str(exc) == "DATABASE_URL is required for the Postgres storage baseline."
    else:
        raise AssertionError("Expected DATABASE_URL to be required.")


def test_oauth_settings_require_public_base_url(monkeypatch) -> None:
    """Ensure OAuth mode fails fast when the public base URL is missing.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If settings do not validate missing OAuth config.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")
    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://demo.authkit.app")
    monkeypatch.delenv("MCP_PUBLIC_BASE_URL", raising=False)

    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert str(exc) == "MCP_PUBLIC_BASE_URL is required when MCP_AUTH_MODE=oauth."
    else:
        raise AssertionError("Expected OAuth settings to require MCP_PUBLIC_BASE_URL.")


def test_oauth_settings_require_authkit_domain(monkeypatch) -> None:
    """Ensure OAuth mode fails fast when the AuthKit domain is missing.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If settings do not validate missing AuthKit config.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")
    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.delenv("WORKOS_AUTHKIT_DOMAIN", raising=False)

    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert str(exc) == (
            "WORKOS_AUTHKIT_DOMAIN is required when MCP_AUTH_MODE=oauth."
        )
    else:
        raise AssertionError(
            "Expected OAuth settings to require WORKOS_AUTHKIT_DOMAIN."
        )


def test_oauth_settings_succeed_with_required_values(monkeypatch) -> None:
    """Ensure OAuth mode loads cleanly when required values are present.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If valid OAuth settings are parsed incorrectly.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")
    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://demo.authkit.app")

    settings = Settings.from_env()

    assert settings.auth_mode == "oauth"
    assert settings.public_base_url == "https://example.com"
    assert settings.workos_authkit_domain == "https://demo.authkit.app"
    assert settings.database_url == "postgresql://demo:demo@localhost:5432/demo"


def test_settings_load_optional_strava_credentials(monkeypatch) -> None:
    """Ensure Strava credentials are optional but loaded when configured.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If Strava env vars are not parsed as expected.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")
    monkeypatch.setenv("STRAVA_CLIENT_ID", " client-id ")
    monkeypatch.setenv("STRAVA_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("STRAVA_REFRESH_TOKEN", "refresh-token")

    settings = Settings.from_env()

    assert settings.strava_client_id == "client-id"
    assert settings.strava_client_secret == "client-secret"
    assert settings.strava_refresh_token == "refresh-token"


def test_settings_do_not_require_strava_credentials(monkeypatch) -> None:
    """Ensure the server can start without Strava sync credentials.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.

    Returns:
        None.

    Raises:
        AssertionError: If missing Strava env vars fail server settings.
    """

    monkeypatch.setenv("DATABASE_URL", "postgresql://demo:demo@localhost:5432/demo")
    monkeypatch.delenv("STRAVA_CLIENT_ID", raising=False)
    monkeypatch.delenv("STRAVA_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("STRAVA_REFRESH_TOKEN", raising=False)

    settings = Settings.from_env()

    assert settings.strava_client_id is None
    assert settings.strava_client_secret is None
    assert settings.strava_refresh_token is None


def test_build_user_store_returns_postgres_store() -> None:
    """Ensure store creation now always targets Postgres.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If the configured storage backend is no longer Postgres.
    """

    settings = Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )

    store = build_user_store(settings)

    assert isinstance(store, PostgresUserStore)
