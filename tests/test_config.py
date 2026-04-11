"""Tests for environment-driven settings resolution."""

from __future__ import annotations

from pathlib import Path

from apex_mcp_server.config import (
    Settings,
    _resolve_auth_mode,
    _resolve_storage_backend,
)
from apex_mcp_server.storage import (
    BlobProfileStore,
    FileProfileStore,
    build_profile_store,
)


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


def test_resolve_storage_backend_uses_file_on_vercel_without_blob_token() -> None:
    """Ensure Vercel previews still boot before Blob is configured.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If preview deployments default to Blob too early.
    """

    backend = _resolve_storage_backend({"VERCEL": "1"})  # type: ignore[arg-type]

    assert backend == "file"


def test_resolve_storage_backend_uses_blob_when_blob_token_exists() -> None:
    """Ensure Vercel auto-selects Blob when the platform token is present.

    Parameters:
        None.

    Returns:
        None.

    Raises:
        AssertionError: If configured Blob deployments fail to use Blob.
    """

    backend = _resolve_storage_backend(  # type: ignore[arg-type]
        {"VERCEL": "1", "VERCEL_BLOB_READ_WRITE_TOKEN": "demo-token"}
    )

    assert backend == "blob"


def test_settings_reads_platform_blob_token(monkeypatch, tmp_path: Path) -> None:
    """Ensure settings normalize the Vercel-injected Blob token variable.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.
        tmp_path: Temporary directory used for the local profiles path.

    Returns:
        None.

    Raises:
        AssertionError: If the normalized settings drop the Blob token.
    """

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("VERCEL_BLOB_READ_WRITE_TOKEN", "demo-token")
    monkeypatch.setenv("PROFILES_DIR", str(tmp_path))

    settings = Settings.from_env()

    assert settings.profile_storage_backend == "blob"
    assert settings.blob_read_write_token == "demo-token"


def test_oauth_settings_require_public_base_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure OAuth mode fails fast when the public base URL is missing.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.
        tmp_path: Temporary directory used for the local profiles path.

    Returns:
        None.

    Raises:
        AssertionError: If settings do not validate missing OAuth config.
    """

    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://demo.authkit.app")
    monkeypatch.setenv("PROFILES_DIR", str(tmp_path))

    try:
        Settings.from_env()
    except RuntimeError as exc:
        assert str(exc) == "MCP_PUBLIC_BASE_URL is required when MCP_AUTH_MODE=oauth."
    else:
        raise AssertionError("Expected OAuth settings to require MCP_PUBLIC_BASE_URL.")


def test_oauth_settings_require_authkit_domain(monkeypatch, tmp_path: Path) -> None:
    """Ensure OAuth mode fails fast when the AuthKit domain is missing.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.
        tmp_path: Temporary directory used for the local profiles path.

    Returns:
        None.

    Raises:
        AssertionError: If settings do not validate missing AuthKit config.
    """

    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("PROFILES_DIR", str(tmp_path))

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


def test_oauth_settings_succeed_with_required_values(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure OAuth mode loads cleanly when required values are present.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.
        tmp_path: Temporary directory used for the local profiles path.

    Returns:
        None.

    Raises:
        AssertionError: If valid OAuth settings are parsed incorrectly.
    """

    monkeypatch.setenv("MCP_AUTH_MODE", "oauth")
    monkeypatch.setenv("MCP_PUBLIC_BASE_URL", "https://example.com")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://demo.authkit.app")
    monkeypatch.setenv("PROFILES_DIR", str(tmp_path))

    settings = Settings.from_env()

    assert settings.auth_mode == "oauth"
    assert settings.public_base_url == "https://example.com"
    assert settings.workos_authkit_domain == "https://demo.authkit.app"


def test_build_profile_store_uses_file_store_on_vercel_without_blob_token(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Ensure Vercel previews can build a store without Blob configuration.

    Parameters:
        monkeypatch: Pytest fixture for temporary environment overrides.
        tmp_path: Temporary directory used for the local profiles path.

    Returns:
        None.

    Raises:
        AssertionError: If store creation still requires Blob in previews.
    """

    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("PROFILES_DIR", str(tmp_path))

    settings = Settings.from_env()
    store = build_profile_store(settings)

    assert isinstance(store, FileProfileStore)
    assert not isinstance(store, BlobProfileStore)
