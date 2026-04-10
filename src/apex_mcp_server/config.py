"""Environment-driven configuration for the FastMCP pilot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

AuthMode = Literal["none", "github"]
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
        >>> raise SettingsError("PUBLIC_BASE_URL is required")
    """


@dataclass(frozen=True, slots=True)
class Settings:
    """Store the runtime settings used to build the server.

    Parameters:
        app_name: Human-readable server name shown to MCP clients.
        version: Version string reported by the server.
        auth_mode: Authentication mode for the server.
        public_base_url: Stable public base URL used for OAuth metadata.
        github_client_id: GitHub OAuth app client identifier.
        github_client_secret: GitHub OAuth app client secret.
        redis_url: Redis URL used for OAuth proxy state on Vercel.
        profile_storage_backend: Storage backend for profile markdown files.
        profiles_dir: Local directory used by the file storage backend.
        blob_prefix: Prefix used for Vercel Blob profile objects.
        blob_read_write_token: Optional explicit Blob token.
        jwt_signing_key: Optional signing key for FastMCP-issued JWTs.

    Returns:
        Settings: Fully normalized server configuration.

    Raises:
        SettingsError: When a required setting is missing in the selected mode.

    Example:
        >>> settings = Settings.from_env()
        >>> settings.auth_mode in {"none", "github"}
        True
    """

    app_name: str
    version: str
    auth_mode: AuthMode
    public_base_url: str | None
    github_client_id: str | None
    github_client_secret: str | None
    redis_url: str | None
    profile_storage_backend: StorageBackend
    profiles_dir: Path
    blob_prefix: str
    blob_read_write_token: str | None
    jwt_signing_key: str | None

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
        public_base_url = _normalize_optional_url(os.environ.get("PUBLIC_BASE_URL"))

        settings = cls(
            app_name=os.environ.get("MCP_SERVER_NAME", "APEX FastMCP Profile Pilot"),
            version=os.environ.get("MCP_SERVER_VERSION", "0.1.0"),
            auth_mode=auth_mode,
            public_base_url=public_base_url,
            github_client_id=_clean_optional_value(os.environ.get("GITHUB_CLIENT_ID")),
            github_client_secret=_clean_optional_value(
                os.environ.get("GITHUB_CLIENT_SECRET")
            ),
            redis_url=_clean_optional_value(os.environ.get("REDIS_URL")),
            profile_storage_backend=storage_backend,
            profiles_dir=Path(
                os.environ.get("PROFILES_DIR", "profiles")
            ).resolve(),
            blob_prefix=os.environ.get("BLOB_PROFILE_PREFIX", "profiles").strip("/"),
            blob_read_write_token=_clean_optional_value(
                os.environ.get("BLOB_READ_WRITE_TOKEN")
            ),
            jwt_signing_key=_clean_optional_value(os.environ.get("JWT_SIGNING_KEY")),
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

        if self.auth_mode == "github":
            _require_value(
                self.public_base_url,
                "PUBLIC_BASE_URL is required when MCP_AUTH_MODE=github.",
            )
            _require_value(
                self.github_client_id,
                "GITHUB_CLIENT_ID is required when MCP_AUTH_MODE=github.",
            )
            _require_value(
                self.github_client_secret,
                "GITHUB_CLIENT_SECRET is required when MCP_AUTH_MODE=github.",
            )
            _require_value(
                self.redis_url,
                "REDIS_URL is required when MCP_AUTH_MODE=github.",
            )

        if self.profile_storage_backend == "blob":
            # The Vercel Blob SDK can read the token from the environment at
            # runtime, so we only enforce a token outside Vercel deployments.
            running_on_vercel = _env_flag(os.environ, "VERCEL")
            if not running_on_vercel and not self.blob_read_write_token:
                raise SettingsError(
                    "BLOB_READ_WRITE_TOKEN is required locally when "
                    "PROFILE_STORAGE_BACKEND=blob."
                )


def _resolve_auth_mode(env: os._Environ[str]) -> AuthMode:
    """Choose the auth mode using explicit config first and safe defaults second.

    Parameters:
        env: Process environment variables.

    Returns:
        AuthMode: Either `"none"` for local development or `"github"` for a
            deployed OAuth flow.

    Raises:
        SettingsError: If the supplied auth mode is not recognized.

    Example:
        >>> _resolve_auth_mode({"MCP_AUTH_MODE": "none"})  # type: ignore[arg-type]
        'none'
    """

    raw_mode = _clean_optional_value(env.get("MCP_AUTH_MODE"))
    if raw_mode:
        if raw_mode not in {"none", "github"}:
            raise SettingsError(
                "MCP_AUTH_MODE must be either 'none' or 'github'."
            )
        return raw_mode  # type: ignore[return-value]

    return "github" if _env_flag(env, "VERCEL") else "none"


def _resolve_storage_backend(env: os._Environ[str]) -> StorageBackend:
    """Choose the profile storage backend.

    Parameters:
        env: Process environment variables.

    Returns:
        StorageBackend: `"file"` for local development or `"blob"` on Vercel by
            default.

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

    return "blob" if _env_flag(env, "VERCEL") else "file"


def _normalize_optional_url(value: str | None) -> str | None:
    """Normalize a possibly-empty URL value.

    Parameters:
        value: Raw environment variable content.

    Returns:
        str | None: The trimmed URL without a trailing slash, or `None`.

    Raises:
        This helper does not raise errors directly.

    Example:
        >>> _normalize_optional_url("https://example.com/")
        'https://example.com'
    """

    cleaned = _clean_optional_value(value)
    if cleaned is None:
        return None
    return cleaned.rstrip("/")


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
