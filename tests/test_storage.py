"""Integration tests for the Postgres-backed storage layer."""

from __future__ import annotations

import os

import asyncpg
import pytest

from apex_mcp_server.models import UserData
from apex_mcp_server.storage import PostgresUserStore

DEFAULT_TEST_DATABASE_URL = "postgresql://apex:apex@127.0.0.1:54329/apex_mcp_server"


class _FakeConnection:
    """Minimal asyncpg-like connection for pool bootstrap unit tests.

    Parameters:
        None.

    Returns:
        _FakeConnection: Connection stub with an `execute` coroutine.

    Raises:
        This helper does not raise errors directly.
    """

    async def execute(self, query: str) -> str:
        """Pretend to execute schema bootstrap SQL.

        Parameters:
            query: SQL statement executed by the store bootstrap.

        Returns:
            str: Static asyncpg-like command tag.

        Raises:
            AssertionError: If the store stops sending schema bootstrap SQL.
        """

        assert "CREATE TABLE IF NOT EXISTS user_profiles" in query
        return "EXECUTE"


class _FakeAcquireContext:
    """Async context manager returned by the fake pool `acquire()` call.

    Parameters:
        connection: Fake connection yielded inside the context block.

    Returns:
        _FakeAcquireContext: Context manager used by `_ensure_pool()`.

    Raises:
        This helper does not raise errors directly.
    """

    def __init__(self, connection: _FakeConnection) -> None:
        """Store the fake connection returned by the async context manager.

        Parameters:
            connection: Fake connection yielded by `__aenter__`.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.
        """

        self.connection = connection

    async def __aenter__(self) -> _FakeConnection:
        """Yield the fake connection inside the async context block.

        Parameters:
            None.

        Returns:
            _FakeConnection: The stub connection used by the test.

        Raises:
            This helper does not raise errors directly.
        """

        return self.connection

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Finish the async context manager without special handling.

        Parameters:
            exc_type: Optional exception type raised inside the context.
            exc: Optional exception instance raised inside the context.
            tb: Optional traceback raised inside the context.

        Returns:
            None.

        Raises:
            This helper does not raise errors directly.
        """


class _FakePool:
    """Minimal pool stub used to unit test asyncpg pool creation options.

    Parameters:
        None.

    Returns:
        _FakePool: Pool stub with `acquire()` and `close()` methods.

    Raises:
        This helper does not raise errors directly.
    """

    def __init__(self) -> None:
        """Create a fake pool with one reusable fake connection.

        Parameters:
            None.

        Returns:
            None.

        Raises:
            This initializer does not raise errors directly.
        """

        self.connection = _FakeConnection()

    def acquire(self) -> _FakeAcquireContext:
        """Return the async context manager used by the storage bootstrap.

        Parameters:
            None.

        Returns:
            _FakeAcquireContext: Async context manager yielding a connection.

        Raises:
            This helper does not raise errors directly.
        """

        return _FakeAcquireContext(self.connection)

    async def close(self) -> None:
        """Mirror asyncpg's `close()` signature for completeness.

        Parameters:
            None.

        Returns:
            None.

        Raises:
            This helper does not raise errors directly.
        """


@pytest.fixture
async def postgres_store() -> PostgresUserStore:
    """Return a Postgres store backed by the local Docker Compose database.

    Parameters:
        None.

    Returns:
        PostgresUserStore: Store instance connected to the configured test DB.

    Raises:
        pytest.skip: When Postgres is not available for integration tests.
    """

    database_url = (
        os.environ.get("TEST_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or DEFAULT_TEST_DATABASE_URL
    )
    store = PostgresUserStore(database_url=database_url)

    try:
        # Touch the database once so we can skip cleanly when Docker is not up.
        await store.get_profile("healthcheck-subject")
    except (OSError, asyncpg.PostgresError) as exc:
        await store.close()
        pytest.skip(f"Postgres integration database is unavailable: {exc}")

    try:
        yield store
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_postgres_store_returns_empty_profile_when_missing(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure a missing profile returns an empty markdown string.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.

    Raises:
        AssertionError: If missing profiles stop returning an empty string.
    """

    loaded_profile = await postgres_store.get_profile(
        "test-missing-profile-subject-v1"
    )

    assert loaded_profile == ""


@pytest.mark.asyncio
async def test_postgres_store_profile_round_trip(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure the Postgres store can write and read markdown profiles.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.

    Raises:
        AssertionError: If the profile round trip does not match expectations.
    """

    subject = "test-profile-round-trip-subject-v1"
    save_result = await postgres_store.set_profile(
        subject,
        "# Persona\nHelpful",
        login="sergio",
    )
    loaded_profile = await postgres_store.get_profile(subject)

    assert save_result.saved is True
    assert save_result.subject == subject
    assert save_result.bytes == len(b"# Persona\nHelpful")
    assert loaded_profile == "# Persona\nHelpful"


@pytest.mark.asyncio
async def test_postgres_store_user_data_round_trip(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure the Postgres store can write and read numeric user data.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.

    Raises:
        AssertionError: If the user-data round trip does not match expectations.
    """

    subject = "test-user-data-round-trip-subject-v1"
    result = await postgres_store.set_user_data(
        subject,
        UserData(weight_kg=68.5, height_cm=174.0, ftp_watts=250),
        login="sergio",
    )
    loaded_data = await postgres_store.get_user_data(subject)

    assert result.saved is True
    assert result.subject == subject
    assert loaded_data.as_dict() == {
        "weight_kg": 68.5,
        "height_cm": 174.0,
        "ftp_watts": 250,
    }


@pytest.mark.asyncio
async def test_postgres_store_updates_user_data_without_erasing_profile(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure markdown and numeric fields can evolve independently.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.

    Raises:
        AssertionError: If writing one field set erases the other.
    """

    subject = "test-independent-updates-subject-v1"
    await postgres_store.set_profile(subject, "# Persona\nStill here", login="sergio")
    await postgres_store.set_user_data(
        subject,
        UserData(weight_kg=70.0, height_cm=175.0, ftp_watts=255),
        login="sergio",
    )

    profile = await postgres_store.get_profile(subject)
    user_data = await postgres_store.get_user_data(subject)

    assert profile == "# Persona\nStill here"
    assert user_data.as_dict() == {
        "weight_kg": 70.0,
        "height_cm": 175.0,
        "ftp_watts": 255,
    }


@pytest.mark.asyncio
async def test_postgres_store_disables_statement_cache_for_pooler_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure asyncpg pool creation stays compatible with Supabase poolers.

    Parameters:
        monkeypatch: Pytest helper used to patch `asyncpg.create_pool`.

    Returns:
        None.

    Raises:
        AssertionError: If pool creation stops disabling statement caching.
    """

    captured_kwargs: dict[str, object] = {}

    async def fake_create_pool(**kwargs: object) -> _FakePool:
        """Capture asyncpg pool options while returning a fake pool.

        Parameters:
            **kwargs: Pool options forwarded by `PostgresUserStore`.

        Returns:
            _FakePool: Pool stub used by `_ensure_pool()`.

        Raises:
            This helper does not raise errors directly.
        """

        captured_kwargs.update(kwargs)
        return _FakePool()

    monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

    store = PostgresUserStore("postgresql://demo:demo@localhost:5432/demo")
    try:
        await store._ensure_pool()
    finally:
        await store.close()

    assert captured_kwargs["statement_cache_size"] == 0
