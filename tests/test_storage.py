"""Integration tests for the Postgres-backed storage layer."""

from __future__ import annotations

import os

import asyncpg
import pytest

from apex_mcp_server.models import UserData
from apex_mcp_server.storage import PostgresUserStore

DEFAULT_TEST_DATABASE_URL = "postgresql://apex:apex@127.0.0.1:54329/apex_mcp_server"


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
