"""Environment-driven configuration for the FastMCP pilot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

AuthMode = Literal["none", "bearer", "oauth"]


class SettingsError(RuntimeError):
    """Raised when required runtime configuration is missing or invalid.

    Parameters:
        None.

    Returns:
        SettingsError: A descriptive configuration error.

    Raises:
        SettingsError: Raised by configuration helpers in this module.

    Example:
        >>> raise SettingsError("DATABASE_URL is required")
    """


@dataclass(frozen=True, slots=True)
class Settings:
    """Store the runtime settings used to build the server.

    Parameters:
        app_name: Human-readable server name shown to MCP clients.
        version: Version string reported by the server.
        auth_mode: Authentication mode for the server.
        api_token: Shared bearer token used to protect the HTTP endpoint.
        public_base_url: Public HTTPS base URL for the deployed MCP server.
        workos_authkit_domain: WorkOS AuthKit domain used for OAuth mode.
        database_url: Shared Postgres connection string used in every
            environment, including local Docker, Vercel, and VM deployments.
        strava_client_id: Optional Strava API client id used only when the
            external sync tool is called with `service="strava"`.
        strava_client_secret: Optional Strava API client secret used only for
            Strava token refresh during activity sync.
        strava_refresh_token: Optional Strava refresh token used to request a
            short-lived access token during activity sync.
        strava_redirect_uri: Optional OAuth callback URI used by the Strava
            browser connection helper.
        strava_scopes: OAuth scopes requested by the Strava browser connection
            helper. `STRAVA_SCOPES` is preferred, while `STRAVA_SCOPE` is
            accepted for compatibility with the simple Strava script.
        strava_token_subject: Storage subject used for the Strava OAuth token
            row. The default keeps Strava as one singleton connection for this
            private pilot.

    Returns:
        Settings: Fully normalized server configuration.

    Raises:
        SettingsError: When a required setting is missing in the selected mode.

    Example:
        >>> settings = Settings.from_env()
        >>> settings.auth_mode in {"none", "bearer", "oauth"}
        True
    """

    app_name: str
    version: str
    auth_mode: AuthMode
    api_token: str | None
    public_base_url: str | None
    workos_authkit_domain: str | None
    database_url: str | None
    strava_client_id: str | None = None
    strava_client_secret: str | None = None
    strava_refresh_token: str | None = None
    strava_redirect_uri: str | None = None
    strava_scopes: str = "read,activity:read_all"
    strava_token_subject: str = "strava-singleton"

    @classmethod
    def from_env(cls) -> Settings:
        """Build normalized settings from environment variables.

        Parameters:
            None.

        Returns:
            Settings: Parsed settings ready for server construction.

        Raises:
            SettingsError: If the selected auth mode or database settings are
                incomplete.

        Example:
            >>> isinstance(Settings.from_env(), Settings)
            True
        """

        settings = cls(
            app_name=os.environ.get("MCP_SERVER_NAME", "APEX FastMCP Profile Pilot"),
            version=os.environ.get("MCP_SERVER_VERSION", "0.1.0"),
            auth_mode=_resolve_auth_mode(os.environ),
            api_token=_clean_optional_value(os.environ.get("MCP_API_TOKEN")),
            public_base_url=_clean_optional_value(
                os.environ.get("MCP_PUBLIC_BASE_URL")
            ),
            workos_authkit_domain=_clean_optional_value(
                os.environ.get("WORKOS_AUTHKIT_DOMAIN")
            ),
            database_url=_clean_optional_value(os.environ.get("DATABASE_URL")),
            strava_client_id=_clean_optional_value(os.environ.get("STRAVA_CLIENT_ID")),
            strava_client_secret=_clean_optional_value(
                os.environ.get("STRAVA_CLIENT_SECRET")
            ),
            strava_refresh_token=_clean_optional_value(
                os.environ.get("STRAVA_REFRESH_TOKEN")
            ),
            strava_redirect_uri=_clean_optional_value(
                os.environ.get("STRAVA_REDIRECT_URI")
            ),
            strava_scopes=(
                _clean_optional_value(os.environ.get("STRAVA_SCOPES"))
                or _clean_optional_value(os.environ.get("STRAVA_SCOPE"))
                or "read,activity:read_all"
            ),
            strava_token_subject=(
                _clean_optional_value(os.environ.get("STRAVA_TOKEN_SUBJECT"))
                or "strava-singleton"
            ),
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
            SettingsError: If the chosen auth mode or database configuration is
                incomplete.

        Example:
            >>> Settings.from_env().validate()
        """

        _require_value(
            self.database_url,
            "DATABASE_URL is required for the Postgres storage baseline.",
        )

        if self.auth_mode == "bearer":
            _require_value(
                self.api_token,
                "MCP_API_TOKEN is required when MCP_AUTH_MODE=bearer.",
            )

        if self.auth_mode == "oauth":
            _require_value(
                self.public_base_url,
                "MCP_PUBLIC_BASE_URL is required when MCP_AUTH_MODE=oauth.",
            )
            _require_value(
                self.workos_authkit_domain,
                "WORKOS_AUTHKIT_DOMAIN is required when MCP_AUTH_MODE=oauth.",
            )


def _resolve_auth_mode(env: os._Environ[str]) -> AuthMode:
    """Choose the auth mode using explicit config first and safe defaults second.

    Parameters:
        env: Process environment variables.

    Returns:
        AuthMode: Either `"none"` for open local development, `"bearer"` for
            the shared-token private mode, or `"oauth"` for the hosted
            Claude.ai-compatible deployment mode.

    Raises:
        SettingsError: If the supplied auth mode is not recognized.

    Example:
        >>> _resolve_auth_mode({"MCP_AUTH_MODE": "none"})  # type: ignore[arg-type]
        'none'
    """

    raw_mode = _clean_optional_value(env.get("MCP_AUTH_MODE"))
    if raw_mode:
        if raw_mode not in {"none", "bearer", "oauth"}:
            raise SettingsError(
                "MCP_AUTH_MODE must be one of 'none', 'bearer', or 'oauth'."
            )
        return raw_mode  # type: ignore[return-value]

    if _clean_optional_value(env.get("MCP_API_TOKEN")):
        return "bearer"

    return "none"


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
