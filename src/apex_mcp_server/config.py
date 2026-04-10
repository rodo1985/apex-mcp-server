"""Environment-driven configuration for the FastMCP pilot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AuthMode = Literal["none", "bearer"]
StorageBackend = Literal["file", "blob"]


class SettingsError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid.

    Parameters:
        None.

    Returns:
        SettingsError: A descriptive configuration error.

    Raises:
        SettingsError: Raised by configuration helpers in this module.

    Example:
        >>> raise SettingsError("MCP_API_TOKEN is required")
    """


@dataclass(frozen=True, slots=True)
class Settings:
    """Store the runtime settings used to build the server.

    Parameters:
        app_name: Human-readable server name shown to MCP clients.
        version: Version string reported by the server.
        auth_mode: Authentication mode for the server.
        api_token: Shared bearer token used to protect the HTTP endpoint.
        profile_storage_backend: Storage backend for profile markdown files.
        profiles_dir: Local directory used by the file storage backend.
        blob_prefix: Prefix used for Vercel Blob profile objects.
        blob_read_write_token: Optional Vercel Blob token. This may come from
            either `BLOB_READ_WRITE_TOKEN` or the platform-injected
            `VERCEL_BLOB_READ_WRITE_TOKEN`.

    Returns:
        Settings: Fully normalized server configuration.

    Raises:
        SettingsError: When a required setting is missing in the selected mode.

    Example:
        >>> settings = Settings.from_env()
        >>> settings.auth_mode in {"none", "bearer"}
        True
    """

    app_name: str
    version: str
    auth_mode: AuthMode
    api_token: str | None
    profile_storage_backend: StorageBackend
    profiles_dir: Path
    blob_prefix: str
    blob_read_write_token: str | None

    @classmethod
    def from_env(cls) -> Settings:
        """Build normalized settings from environment variables.

        Parameters:
            None.

        Returns:
            Settings: Parsed settings ready for server construction.

        Raises:
            SettingsError: If the selected auth or storage backend is missing
                required environment variables.

        Example:
            >>> isinstance(Settings.from_env(), Settings)
            True
        """

        auth_mode = _resolve_auth_mode(os.environ)
        storage_backend = _resolve_storage_backend(os.environ)

        settings = cls(
            app_name=os.environ.get("MCP_SERVER_NAME", "APEX FastMCP Profile Pilot"),
            version=os.environ.get("MCP_SERVER_VERSION", "0.1.0"),
            auth_mode=auth_mode,
            api_token=_clean_optional_value(os.environ.get("MCP_API_TOKEN")),
            profile_storage_backend=storage_backend,
            profiles_dir=Path(
                os.environ.get("PROFILES_DIR", "profiles")
            ).resolve(),
            blob_prefix=os.environ.get("BLOB_PROFILE_PREFIX", "profiles").strip("/"),
            blob_read_write_token=_resolve_blob_token(os.environ),
        )

        settings.validate()
        return settings

    def validate(self) -> None:
        """Validate cross-field configuration requirements.

        Parameters:
            None.

        Returns:
            None: Validation happens for side effects only.

        Raises:
            SettingsError: If the chosen auth or storage mode is incomplete.

        Example:
            >>> Settings.from_env().validate()
        """

        if self.auth_mode == "bearer":
            _require_value(
                self.api_token,
                "MCP_API_TOKEN is required when MCP_AUTH_MODE=bearer.",
            )

        if self.profile_storage_backend == "blob":
            _require_value(
                self.blob_read_write_token,
                "A Vercel Blob token is required when "
                "PROFILE_STORAGE_BACKEND=blob. Set BLOB_READ_WRITE_TOKEN or "
                "VERCEL_BLOB_READ_WRITE_TOKEN.",
            )


def _resolve_auth_mode(env: os._Environ[str]) -> AuthMode:
    """Choose the auth mode using explicit config first and safe defaults second.

    Parameters:
        env: Process environment variables.

    Returns:
        AuthMode: Either `"none"` for open local development or `"bearer"` for
            the shared-token private mode.

    Raises:
        SettingsError: If the supplied auth mode is not recognized.

    Example:
        >>> _resolve_auth_mode({"MCP_AUTH_MODE": "none"})  # type: ignore[arg-type]
        'none'
    """

    raw_mode = _clean_optional_value(env.get("MCP_AUTH_MODE"))
    if raw_mode:
        if raw_mode not in {"none", "bearer"}:
            raise SettingsError("MCP_AUTH_MODE must be either 'none' or 'bearer'.")
        return raw_mode  # type: ignore[return-value]

    if _clean_optional_value(env.get("MCP_API_TOKEN")):
        return "bearer"

    return "none"


def _resolve_storage_backend(env: os._Environ[str]) -> StorageBackend:
    """Choose the profile storage backend.

    Parameters:
        env: Process environment variables.

    Returns:
        StorageBackend: `"file"` for local development, or `"blob"` on Vercel
            only when Blob has actually been configured.

    Raises:
        SettingsError: If the supplied backend is not recognized.

    Example:
        >>> _resolve_storage_backend(
        ...     {"PROFILE_STORAGE_BACKEND": "file"}  # type: ignore[arg-type]
        ... )
        'file'
    """

    raw_backend = _clean_optional_value(env.get("PROFILE_STORAGE_BACKEND"))
    if raw_backend:
        if raw_backend not in {"file", "blob"}:
            raise SettingsError(
                "PROFILE_STORAGE_BACKEND must be either 'file' or 'blob'."
            )
        return raw_backend  # type: ignore[return-value]

    # Preview deployments should still boot even before Blob is configured, so
    # we only auto-select Blob when a token is present. Otherwise we fall back
    # to ephemeral file storage, which is good enough for a hello-world deploy.
    if _env_flag(env, "VERCEL") and _has_blob_configuration(env):
        return "blob"

    return "file"


def _resolve_blob_token(env: os._Environ[str]) -> str | None:
    """Return the first configured Vercel Blob token from supported env vars.

    Parameters:
        env: Process environment variables.

    Returns:
        str | None: A normalized Blob token, or `None` when neither the local
            nor the Vercel-injected variable is present.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _resolve_blob_token(
        ...     {"VERCEL_BLOB_READ_WRITE_TOKEN": "demo"}  # type: ignore[arg-type]
        ... )
        'demo'
    """

    return _clean_optional_value(
        env.get("BLOB_READ_WRITE_TOKEN")
    ) or _clean_optional_value(
        env.get("VERCEL_BLOB_READ_WRITE_TOKEN")
    )


def _has_blob_configuration(env: os._Environ[str]) -> bool:
    """Report whether the environment contains enough Blob config to auto-use it.

    Parameters:
        env: Process environment variables.

    Returns:
        bool: `True` when a supported Blob token is present.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _has_blob_configuration(
        ...     {"BLOB_READ_WRITE_TOKEN": "demo"}  # type: ignore[arg-type]
        ... )
        True
    """

    return _resolve_blob_token(env) is not None


def _clean_optional_value(value: str | None) -> str | None:
    """Convert empty environment variable values into `None`.

    Parameters:
        value: Raw environment variable content.

    Returns:
        str | None: A trimmed non-empty string or `None`.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _clean_optional_value("  demo  ")
        'demo'
    """

    if value is None:
        return None

    cleaned = value.strip()
    return cleaned or None


def _env_flag(env: os._Environ[str], name: str) -> bool:
    """Interpret a common environment boolean flag.

    Parameters:
        env: Process environment variables.
        name: Environment variable name to inspect.

    Returns:
        bool: `True` when the variable represents an enabled flag.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _env_flag({"VERCEL": "1"}, "VERCEL")  # type: ignore[arg-type]
        True
    """

    raw_value = _clean_optional_value(env.get(name))
    if raw_value is None:
        return False
    return raw_value.lower() not in {"0", "false", "no", "off"}


def _require_value(value: str | None, message: str) -> None:
    """Raise a configuration error when a required value is missing.

    Parameters:
        value: Candidate value that must be present.
        message: Error message raised when the value is missing.

    Returns:
        None: Validation happens for side effects only.

    Raises:
        SettingsError: If `value` is empty or missing.

    Example:
        >>> _require_value("ok", "missing")
    """

    if not value:
        raise SettingsError(message)
