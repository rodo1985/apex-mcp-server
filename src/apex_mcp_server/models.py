"""Small shared models for the profile pilot."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SaveResult:
    """Describe the outcome of saving a profile document.

    Parameters:
        saved: Whether the write completed successfully.
        pathname: Storage pathname used for the saved profile.
        bytes: Number of UTF-8 bytes written.

    Returns:
        SaveResult: A lightweight container used by MCP tools.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> SaveResult(saved=True, pathname="profiles/github-123.md", bytes=12)
        SaveResult(saved=True, pathname='profiles/github-123.md', bytes=12)
    """

    saved: bool
    pathname: str
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
            >>> SaveResult(True, "profiles/github-1.md", 20).as_dict()
            {'saved': True, 'pathname': 'profiles/github-1.md', 'bytes': 20}
        """

        return {
            "saved": self.saved,
            "pathname": self.pathname,
            "bytes": self.bytes,
        }


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """Represent the caller identity resolved for the current MCP request.

    Parameters:
        authenticated: Whether the request carried a verified access token.
        subject: Stable upstream subject claim when available.
        login: Human-readable login or username when available.
        user_key: Stable storage key used for the profile document.
        request_id: Current FastMCP request identifier for diagnostics.

    Returns:
        UserIdentity: A normalized identity structure used by tools, resources,
            and prompts.

    Raises:
        This dataclass does not raise errors directly.

    Example:
        >>> UserIdentity(True, "123", "octocat", "github-123", "req-1")
        UserIdentity(
        ...     authenticated=True,
        ...     subject='123',
        ...     login='octocat',
        ...     user_key='github-123',
        ...     request_id='req-1',
        ... )
    """

    authenticated: bool
    subject: str | None
    login: str | None
    user_key: str
    request_id: str

    def as_whoami_response(self) -> dict[str, object]:
        """Return the user-facing identity payload for the `whoami` tool.

        Parameters:
            None.

        Returns:
            dict[str, object]: The public diagnostic shape exposed by the pilot.

        Raises:
            This method does not raise errors directly.

        Example:
            >>> identity = UserIdentity(False, None, None, "anonymous", "req-1")
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
