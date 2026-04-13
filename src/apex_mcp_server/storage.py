"""Postgres-backed storage for the FastMCP pilot."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod

import asyncpg

from apex_mcp_server.config import Settings
from apex_mcp_server.models import (
    ProfileSaveResult,
    UserData,
    UserDataSaveResult,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS user_profiles (
    subject TEXT PRIMARY KEY,
    login TEXT,
    profile_markdown TEXT NOT NULL DEFAULT '',
    weight_kg DOUBLE PRECISION,
    height_cm DOUBLE PRECISION,
    ftp_watts INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
""".strip()


class UserStore(ABC):
    """Define the read/write contract for persisted user data.

    Parameters:
        None.

    Returns:
        UserStore: An abstract interface implemented by concrete backends.

    Raises:
        This abstract base class does not raise errors directly.

    Example:
        >>> isinstance(UserStore.__mro__[0], type)
        True
    """

    @abstractmethod
    async def get_profile(self, subject: str) -> str:
        """Read the saved markdown profile for a subject.

        Parameters:
            subject: Stable database subject for the profile owner.

        Returns:
            str: Markdown profile content, or an empty string when missing.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """

    @abstractmethod
    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the markdown profile for a subject.

        Parameters:
            subject: Stable database subject for the profile owner.
            profile_markdown: New markdown content to persist.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Summary of the write operation.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """

    @abstractmethod
    async def get_user_data(self, subject: str) -> UserData:
        """Read the saved numeric user data for a subject.

        Parameters:
            subject: Stable database subject for the row owner.

        Returns:
            UserData: Stored numeric fields, or `None` values when missing.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """

    @abstractmethod
    async def set_user_data(
        self,
        subject: str,
        data: UserData,
        login: str | None = None,
    ) -> UserDataSaveResult:
        """Overwrite the numeric user data for a subject.

        Parameters:
            subject: Stable database subject for the row owner.
            data: Numeric user data to persist.
            login: Optional friendly login captured from the auth layer.

        Returns:
            UserDataSaveResult: Summary of the completed write.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any backend resources such as database pools.

        Parameters:
            None.

        Returns:
            None.

        Raises:
            Exception: Concrete backends may raise backend-specific errors.
        """


class PostgresUserStore(UserStore):
    """Persist profile and user data in a shared Postgres table.

    Parameters:
        database_url: Async Postgres connection string.
        schema_sql: SQL used to bootstrap the single-table baseline.

    Returns:
        PostgresUserStore: A storage backend that works the same way locally,
            on Vercel, or on a VM as long as `DATABASE_URL` is available.

    Raises:
        Exception: The underlying Postgres driver may raise connection or query
            errors.

    Example:
        >>> store = PostgresUserStore("postgresql://demo:demo@localhost:5432/demo")
        >>> store.database_url.startswith("postgresql://")
        True
    """

    def __init__(self, database_url: str, schema_sql: str = SCHEMA_SQL) -> None:
        """Store the connection settings and bootstrap SQL.

        Parameters:
            database_url: Async Postgres connection string.
            schema_sql: SQL used to create the baseline table if needed.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.
        """

        self.database_url = database_url
        self.schema_sql = schema_sql
        self._pool: asyncpg.Pool | None = None
        self._pool_lock = asyncio.Lock()

    async def get_profile(self, subject: str) -> str:
        """Read the markdown profile stored for a subject.

        Parameters:
            subject: Stable database subject for the profile owner.

        Returns:
            str: Stored markdown, or an empty string when no row exists yet.

        Raises:
            Exception: Propagated from asyncpg when the query fails.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(PostgresUserStore.get_profile)
            True
        """

        row = await self._fetchrow(
            "SELECT profile_markdown FROM user_profiles WHERE subject = $1",
            subject,
        )
        if row is None:
            return ""
        return str(row["profile_markdown"] or "")

    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the markdown profile stored for a subject.

        Parameters:
            subject: Stable database subject for the profile owner.
            profile_markdown: Markdown content to persist.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Summary of the completed write.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._execute(
            """
            INSERT INTO user_profiles (subject, login, profile_markdown)
            VALUES ($1, $2, $3)
            ON CONFLICT (subject) DO UPDATE
            SET
                login = COALESCE(EXCLUDED.login, user_profiles.login),
                profile_markdown = EXCLUDED.profile_markdown,
                updated_at = NOW()
            """,
            subject,
            login,
            profile_markdown,
        )

        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(profile_markdown.encode("utf-8")),
        )

    async def get_user_data(self, subject: str) -> UserData:
        """Read the numeric user data stored for a subject.

        Parameters:
            subject: Stable database subject for the row owner.

        Returns:
            UserData: Stored numeric values, or `None` values when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT weight_kg, height_cm, ftp_watts
            FROM user_profiles
            WHERE subject = $1
            """,
            subject,
        )
        if row is None:
            return UserData(weight_kg=None, height_cm=None, ftp_watts=None)

        return UserData(
            weight_kg=_as_float(row["weight_kg"]),
            height_cm=_as_float(row["height_cm"]),
            ftp_watts=_as_int(row["ftp_watts"]),
        )

    async def set_user_data(
        self,
        subject: str,
        data: UserData,
        login: str | None = None,
    ) -> UserDataSaveResult:
        """Overwrite the numeric user data stored for a subject.

        Parameters:
            subject: Stable database subject for the row owner.
            data: Numeric user data to persist.
            login: Optional friendly login captured from the auth layer.

        Returns:
            UserDataSaveResult: Summary of the completed write.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._execute(
            """
            INSERT INTO user_profiles (
                subject,
                login,
                weight_kg,
                height_cm,
                ftp_watts
            )
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (subject) DO UPDATE
            SET
                login = COALESCE(EXCLUDED.login, user_profiles.login),
                weight_kg = EXCLUDED.weight_kg,
                height_cm = EXCLUDED.height_cm,
                ftp_watts = EXCLUDED.ftp_watts,
                updated_at = NOW()
            """,
            subject,
            login,
            data.weight_kg,
            data.height_cm,
            data.ftp_watts,
        )

        return UserDataSaveResult(
            saved=True,
            subject=subject,
            weight_kg=data.weight_kg,
            height_cm=data.height_cm,
            ftp_watts=data.ftp_watts,
        )

    async def close(self) -> None:
        """Release the asyncpg pool when tests or scripts are finished.

        Parameters:
            None.

        Returns:
            None.

        Raises:
            Exception: Propagated from asyncpg when the pool close fails.
        """

        if self._pool is None:
            return

        await self._pool.close()
        self._pool = None

    async def _execute(self, query: str, *args: object) -> str:
        """Run a write statement after ensuring the pool and schema exist.

        Parameters:
            query: SQL statement to execute.
            *args: Positional query parameters.

        Returns:
            str: asyncpg command tag returned by the executed statement.

        Raises:
            Exception: Propagated from asyncpg when the statement fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def _fetchrow(
        self,
        query: str,
        *args: object,
    ) -> asyncpg.Record | None:
        """Run a read query after ensuring the pool and schema exist.

        Parameters:
            query: SQL statement to execute.
            *args: Positional query parameters.

        Returns:
            asyncpg.Record | None: First matching row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the statement fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def _ensure_pool(self) -> asyncpg.Pool:
        """Create the asyncpg pool and bootstrap the schema on first use.

        Parameters:
            None.

        Returns:
            asyncpg.Pool: Ready-to-use Postgres connection pool.

        Raises:
            Exception: Propagated from asyncpg when pool creation fails.
        """

        if self._pool is not None:
            return self._pool

        async with self._pool_lock:
            if self._pool is None:
                self._pool = await asyncpg.create_pool(
                    dsn=self.database_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=30,
                )

                # Remote environments such as Vercel do not run the Docker init
                # script, so we keep the bootstrap SQL here as well. The schema
                # is intentionally tiny, so this stays easy to reason about.
                async with self._pool.acquire() as connection:
                    await connection.execute(self.schema_sql)

        return self._pool


def build_user_store(settings: Settings) -> UserStore:
    """Create the configured Postgres-backed user store.

    Parameters:
        settings: Normalized runtime settings.

    Returns:
        UserStore: The Postgres storage backend used by the pilot.

    Raises:
        RuntimeError: Propagated if the database URL is unexpectedly missing.

    Example:
        >>> isinstance(build_user_store(Settings.from_env()), UserStore)
        True
    """

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL must be validated before building the store.")

    return PostgresUserStore(database_url=settings.database_url)


def _as_float(value: object | None) -> float | None:
    """Convert nullable database numeric values into Python floats.

    Parameters:
        value: Raw nullable value returned by asyncpg.

    Returns:
        float | None: Normalized float for MCP responses.

    Raises:
        ValueError: If the provided value cannot be converted to `float`.
    """

    if value is None:
        return None
    return float(value)


def _as_int(value: object | None) -> int | None:
    """Convert nullable database numeric values into Python integers.

    Parameters:
        value: Raw nullable value returned by asyncpg.

    Returns:
        int | None: Normalized integer for MCP responses.

    Raises:
        ValueError: If the provided value cannot be converted to `int`.
    """

    if value is None:
        return None
    return int(value)
