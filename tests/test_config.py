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
