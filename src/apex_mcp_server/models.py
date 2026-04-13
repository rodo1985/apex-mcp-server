"""Small shared models for the Postgres-backed MCP pilot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileSaveResult:
    """Describe the outcome of saving a markdown profile.

    Parameters:
        saved: Whether the write completed successfully.
        subject: Subject that owns the saved row.
        bytes: Number of UTF-8 bytes written into `profile_markdown`.

    Returns:
        ProfileSaveResult: A lightweight container used by the profile tool.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> ProfileSaveResult(saved=True, subject="anonymous", bytes=12)
        ProfileSaveResult(saved=True, subject='anonymous', bytes=12)
    """

    saved: bool
    subject: str
    bytes: int

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the save result.

        Parameters:
            None.

        Returns:
            dict[str, object]: A dictionary safe to return from MCP tools.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> ProfileSaveResult(True, "anonymous", 20).as_dict()
            {'saved': True, 'subject': 'anonymous', 'bytes': 20}
        """

        return {
            "saved": self.saved,
            "subject": self.subject,
            "bytes": self.bytes,
        }


@dataclass(frozen=True, slots=True)
class UserData:
    """Represent the small tabular user data stored alongside the profile.

    Parameters:
        weight_kg: Optional body weight in kilograms.
        height_cm: Optional height in centimeters.
        ftp_watts: Optional functional threshold power in watts.

    Returns:
        UserData: A normalized view of the numeric user fields.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> UserData(weight_kg=68.5, height_cm=174.0, ftp_watts=250)
        UserData(weight_kg=68.5, height_cm=174.0, ftp_watts=250)
    """

    weight_kg: float | None
    height_cm: float | None
    ftp_watts: int | None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the numeric data.

        Parameters:
            None.

        Returns:
            dict[str, object]: Numeric user fields ready for MCP tool output.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> UserData(68.5, 174.0, 250).as_dict()
            {'weight_kg': 68.5, 'height_cm': 174.0, 'ftp_watts': 250}
        """

        return {
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "ftp_watts": self.ftp_watts,
        }


@dataclass(frozen=True, slots=True)
class UserDataSaveResult:
    """Describe the outcome of saving tabular user data.

    Parameters:
        saved: Whether the write completed successfully.
        subject: Subject that owns the saved row.
        weight_kg: Stored body weight in kilograms.
        height_cm: Stored height in centimeters.
        ftp_watts: Stored functional threshold power in watts.

    Returns:
        UserDataSaveResult: A lightweight container used by the user-data tool.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> UserDataSaveResult(True, "anonymous", 68.5, 174.0, 250)
        UserDataSaveResult(
        ...     saved=True,
        ...     subject='anonymous',
        ...     weight_kg=68.5,
        ...     height_cm=174.0,
        ...     ftp_watts=250,
        ... )
    """

    saved: bool
    subject: str
    weight_kg: float | None
    height_cm: float | None
    ftp_watts: int | None

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-serializable representation of the save result.

        Parameters:
            None.

        Returns:
            dict[str, object]: Result payload safe to return from MCP tools.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> UserDataSaveResult(True, "anonymous", 68.5, 174.0, 250).as_dict()
            {
            ...     'saved': True,
            ...     'subject': 'anonymous',
            ...     'weight_kg': 68.5,
            ...     'height_cm': 174.0,
            ...     'ftp_watts': 250,
            ... }
        """

        return {
            "saved": self.saved,
            "subject": self.subject,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "ftp_watts": self.ftp_watts,
        }


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """Represent the caller identity resolved for the current MCP request.

    Parameters:
        authenticated: Whether the request carried a verified access token.
        subject: Stable upstream subject claim when available.
        login: Human-readable login or username when available.
        request_id: Current FastMCP request identifier for diagnostics.

    Returns:
        UserIdentity: A normalized identity structure used by tools, resources,
            and prompts.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> UserIdentity(True, "private-profile", None, "req-1")
        UserIdentity(
        ...     authenticated=True,
        ...     subject='private-profile',
        ...     login=None,
        ...     request_id='req-1',
        ... )
    """

    authenticated: bool
    subject: str | None
    login: str | None
    request_id: str

    def storage_subject(self) -> str:
        """Return the database subject used for persisted user records.

        Parameters:
            None.

        Returns:
            str: The authenticated subject, or `anonymous` in local no-auth
                mode.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> UserIdentity(False, None, None, "req-1").storage_subject()
            'anonymous'
        """

        return self.subject or "anonymous"

    def as_whoami_response(self) -> dict[str, object]:
        """Return the user-facing identity payload for the `whoami` tool.

        Parameters:
            None.

        Returns:
            dict[str, object]: The public diagnostic shape exposed by the pilot.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> identity = UserIdentity(False, None, None, "req-1")
            >>> identity.as_whoami_response()
            {
            ...     'authenticated': False,
            ...     'subject': None,
            ...     'login': None,
            ...     'request_id': 'req-1',
            ... }
        """

        return {
            "authenticated": self.authenticated,
            "subject": self.subject,
            "login": self.login,
            "request_id": self.request_id,
        }
