"""Integration tests for the Postgres-backed wellness storage layer."""

from __future__ import annotations

import os
from uuid import uuid4

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
    """

    async def execute(self, query: str) -> str:
        """Pretend to execute schema bootstrap SQL.

        Parameters:
            query: SQL statement executed by the store bootstrap.

        Returns:
            str: Static asyncpg-like command tag.

        Raises:
            AssertionError: If schema bootstrap stops covering key tables.
        """

        assert "CREATE TABLE IF NOT EXISTS user_profiles" in query
        assert "CREATE TABLE IF NOT EXISTS food_products" in query
        assert "usage_count INTEGER NOT NULL DEFAULT 0" in query
        assert "CREATE TABLE IF NOT EXISTS daily_metrics" in query
        assert "CREATE TABLE IF NOT EXISTS external_service_tokens" in query
        assert "CREATE TABLE IF NOT EXISTS memory_items" in query
        return "EXECUTE"


class _FakeAcquireContext:
    """Async context manager returned by the fake pool `acquire()` call.

    Parameters:
        connection: Fake connection yielded inside the context block.

    Returns:
        _FakeAcquireContext: Context manager used by `_ensure_pool()`.
    """

    def __init__(self, connection: _FakeConnection) -> None:
        """Store the fake connection returned by the async context manager.

        Parameters:
            connection: Fake connection yielded by `__aenter__`.

        Returns:
            None.
        """

        self.connection = connection

    async def __aenter__(self) -> _FakeConnection:
        """Yield the fake connection inside the async context block.

        Parameters:
            None.

        Returns:
            _FakeConnection: The stub connection used by the test.
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
        """


class _FakePool:
    """Minimal pool stub used to unit test asyncpg pool creation options.

    Parameters:
        None.

    Returns:
        _FakePool: Pool stub with `acquire()` and `close()` methods.
    """

    def __init__(self) -> None:
        """Create a fake pool with one reusable fake connection.

        Parameters:
            None.

        Returns:
            None.
        """

        self.connection = _FakeConnection()

    def acquire(self) -> _FakeAcquireContext:
        """Return the async context manager used by the storage bootstrap.

        Parameters:
            None.

        Returns:
            _FakeAcquireContext: Async context manager yielding a connection.
        """

        return _FakeAcquireContext(self.connection)

    async def close(self) -> None:
        """Mirror asyncpg's `close()` signature for completeness.

        Parameters:
            None.

        Returns:
            None.
        """


def make_subject(prefix: str) -> str:
    """Return a unique subject string so integration tests stay isolated.

    Parameters:
        prefix: Human-readable prefix describing the test.

    Returns:
        str: Unique subject string safe to reuse in a shared database.
    """

    return f"{prefix}-{uuid4().hex[:12]}"


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
        await store.get_profile("healthcheck-subject-v2")
    except (OSError, asyncpg.PostgresError) as exc:
        await store.close()
        pytest.skip(f"Postgres integration database is unavailable: {exc}")

    try:
        yield store
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_postgres_store_keeps_existing_profile_and_user_data_behavior(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure singleton documents extend the baseline without breaking v1 data.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("singleton")
    await postgres_store.set_profile(subject, "# Persona\nHelpful", login="sergio")
    await postgres_store.set_user_data(
        subject,
        UserData(weight_kg=68.5, height_cm=174.0, ftp_watts=250),
        login="sergio",
    )
    diet_preferences = await postgres_store.set_diet_preferences(
        subject,
        "Prefer Mediterranean-style meals.",
        login="sergio",
    )
    diet_goals = await postgres_store.set_diet_goals(
        subject,
        "Maintain a mild daily calorie deficit.",
        login="sergio",
    )
    training_goals = await postgres_store.set_training_goals(
        subject,
        "Keep long rides and quality running sessions consistent.",
        login="sergio",
    )

    loaded_profile = await postgres_store.get_profile(subject)
    loaded_user_data = await postgres_store.get_user_data(subject)
    loaded_diet_preferences = await postgres_store.get_diet_preferences(subject)
    loaded_diet_goals = await postgres_store.get_diet_goals(subject)
    loaded_training_goals = await postgres_store.get_training_goals(subject)

    assert loaded_profile == "# Persona\nHelpful"
    assert loaded_user_data.as_dict() == {
        "weight_kg": 68.5,
        "height_cm": 174.0,
        "ftp_watts": 250,
    }
    assert loaded_diet_preferences == "Prefer Mediterranean-style meals."
    assert loaded_diet_goals == "Maintain a mild daily calorie deficit."
    assert (
        loaded_training_goals
        == "Keep long rides and quality running sessions consistent."
    )
    assert diet_preferences.saved is True
    assert diet_goals.saved is True
    assert training_goals.saved is True


@pytest.mark.asyncio
async def test_postgres_store_products_support_crud_and_unique_names(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure the product catalog supports CRUD and per-user unique names.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("products")
    other_subject = make_subject("products-other")

    product = await postgres_store.add_product(
        subject,
        name="Oats",
        default_serving_g=60.0,
        calories_per_100g=389.0,
        carbs_g_per_100g=66.0,
        protein_g_per_100g=17.0,
        fat_g_per_100g=7.0,
        notes_markdown="Breakfast staple",
    )
    listed_products = await postgres_store.list_products(subject)
    loaded_product = await postgres_store.get_product(subject, int(product["id"]))
    updated_product = await postgres_store.update_product(
        subject,
        product_id=int(product["id"]),
        name="Rolled oats",
        default_serving_g=70.0,
        calories_per_100g=389.0,
        carbs_g_per_100g=66.0,
        protein_g_per_100g=17.0,
        fat_g_per_100g=7.0,
        notes_markdown="Updated",
    )

    with pytest.raises(asyncpg.UniqueViolationError):
        await postgres_store.add_product(
            subject,
            name="Rolled oats",
            default_serving_g=50.0,
            calories_per_100g=300.0,
            carbs_g_per_100g=50.0,
            protein_g_per_100g=10.0,
            fat_g_per_100g=4.0,
        )

    other_product = await postgres_store.add_product(
        other_subject,
        name="Rolled oats",
        default_serving_g=None,
        calories_per_100g=389.0,
        carbs_g_per_100g=66.0,
        protein_g_per_100g=17.0,
        fat_g_per_100g=7.0,
    )
    foreign_lookup = await postgres_store.get_product(other_subject, int(product["id"]))
    delete_result = await postgres_store.delete_product(subject, int(product["id"]))

    assert product["name"] == "Oats"
    assert product["usage_count"] == 0
    assert listed_products[0]["id"] == product["id"]
    assert listed_products[0]["usage_count"] == 0
    assert loaded_product is not None and loaded_product["name"] == "Oats"
    assert loaded_product["usage_count"] == 0
    assert updated_product is not None and updated_product["name"] == "Rolled oats"
    assert updated_product["usage_count"] == 0
    assert other_product["name"] == "Rolled oats"
    assert other_product["usage_count"] == 0
    assert foreign_lookup is None
    assert delete_result == {"deleted": True, "product_id": int(product["id"])}


@pytest.mark.asyncio
async def test_postgres_store_daily_targets_are_upserted_per_user_and_day(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure one user/day pair maps to one target row with upsert semantics.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("targets")

    first = await postgres_store.set_daily_target(
        subject,
        target_date="2026-04-14",
        target_food_calories=2200.0,
        target_exercise_calories=500.0,
        target_protein_g=150.0,
        target_carbs_g=250.0,
        target_fat_g=60.0,
        notes_markdown="Base plan",
    )
    second = await postgres_store.set_daily_target(
        subject,
        target_date="2026-04-14",
        target_food_calories=2300.0,
        target_exercise_calories=650.0,
        target_protein_g=155.0,
        target_carbs_g=275.0,
        target_fat_g=62.0,
        notes_markdown="Long ride adjustment",
    )

    listed_targets = await postgres_store.list_daily_targets(subject)
    loaded_target = await postgres_store.get_daily_target(subject, "2026-04-14")

    assert first["id"] == second["id"]
    assert len(listed_targets) == 1
    assert loaded_target is not None
    assert loaded_target["target_food_calories"] == 2300.0
    assert loaded_target["target_exercise_calories"] == 650.0
    assert loaded_target["notes_markdown"] == "Long ride adjustment"


@pytest.mark.asyncio
async def test_postgres_store_daily_metrics_are_upserted_per_user_day_and_type(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure daily metrics use one row per user, day, and metric type.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("metrics")
    other_subject = make_subject("metrics-other")

    first_weight = await postgres_store.set_daily_metric(
        subject,
        metric_date="2026-04-14",
        metric_type=" Weight ",
        value=68.5,
    )
    updated_weight = await postgres_store.set_daily_metric(
        subject,
        metric_date="2026-04-14",
        metric_type="weight",
        value=69.0,
    )
    steps = await postgres_store.set_daily_metric(
        subject,
        metric_date="2026-04-14",
        metric_type="steps",
        value=12000.0,
    )
    sleep = await postgres_store.set_daily_metric(
        subject,
        metric_date="2026-04-15",
        metric_type="sleep_hours",
        value=7.5,
    )

    loaded_weight = await postgres_store.get_daily_metric(
        subject,
        "2026-04-14",
        "WEIGHT",
    )
    foreign_weight = await postgres_store.get_daily_metric(
        other_subject,
        "2026-04-14",
        "weight",
    )
    listed_range = await postgres_store.list_daily_metrics(
        subject,
        date_from="2026-04-14",
        date_to="2026-04-14",
    )
    listed_weight = await postgres_store.list_daily_metrics(
        subject,
        metric_type="weight",
    )
    deleted_sleep = await postgres_store.delete_daily_metric(
        subject,
        "2026-04-15",
        "sleep_hours",
    )

    assert first_weight["id"] == updated_weight["id"]
    assert steps["id"] != updated_weight["id"]
    assert sleep["metric_date"] == "2026-04-15"
    assert loaded_weight is not None
    assert loaded_weight["metric_type"] == "weight"
    assert loaded_weight["value"] == 69.0
    assert foreign_weight is None
    assert {item["metric_type"] for item in listed_range} == {"steps", "weight"}
    assert len(listed_weight) == 1
    assert listed_weight[0]["value"] == 69.0
    assert deleted_sleep == {
        "deleted": True,
        "metric_date": "2026-04-15",
        "metric_type": "sleep_hours",
    }
    assert (
        await postgres_store.get_daily_metric(subject, "2026-04-15", "sleep_hours")
        is None
    )


@pytest.mark.asyncio
async def test_postgres_store_daily_metric_validation_is_clear(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure daily metric type and value validation raises clear errors.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("metric-validation")

    with pytest.raises(ValueError, match="Unsupported metric_type"):
        await postgres_store.set_daily_metric(
            subject,
            metric_date="2026-04-14",
            metric_type="mood",
            value=3.0,
        )

    with pytest.raises(ValueError, match="weight value must be greater than 0"):
        await postgres_store.set_daily_metric(
            subject,
            metric_date="2026-04-14",
            metric_type="weight",
            value=-1.0,
        )

    with pytest.raises(ValueError, match="steps value must be a whole number"):
        await postgres_store.set_daily_metric(
            subject,
            metric_date="2026-04-14",
            metric_type="steps",
            value=12.5,
        )

    with pytest.raises(ValueError, match="sleep_hours value must be between 0 and 24"):
        await postgres_store.set_daily_metric(
            subject,
            metric_date="2026-04-14",
            metric_type="sleep_hours",
            value=24.5,
        )

    with pytest.raises(ValueError, match="value must be a finite number"):
        await postgres_store.set_daily_metric(
            subject,
            metric_date="2026-04-14",
            metric_type="weight",
            value=float("nan"),
        )


@pytest.mark.asyncio
async def test_postgres_store_meals_and_items_keep_historical_nutrition_snapshots(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure meal items snapshot product nutrition instead of live-linking it.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("meals")

    product = await postgres_store.add_product(
        subject,
        name="Oats",
        default_serving_g=60.0,
        calories_per_100g=389.0,
        carbs_g_per_100g=66.0,
        protein_g_per_100g=17.0,
        fat_g_per_100g=7.0,
        notes_markdown="Breakfast staple",
    )
    meal = await postgres_store.add_meal(
        subject,
        meal_date="2026-04-14",
        meal_label="Breakfast",
        notes_markdown="Pre-ride meal",
    )
    meal_item = await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=80.0,
    )
    manual_item = await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        grams=30.0,
        ingredient_name="Honey",
        calories=91.0,
        carbs_g=24.0,
        protein_g=0.0,
        fat_g=0.0,
    )

    await postgres_store.update_product(
        subject,
        product_id=int(product["id"]),
        name="Oats updated",
        default_serving_g=70.0,
        calories_per_100g=450.0,
        carbs_g_per_100g=70.0,
        protein_g_per_100g=20.0,
        fat_g_per_100g=8.0,
        notes_markdown="Changed nutrition",
    )
    loaded_meal = await postgres_store.get_meal(subject, int(meal["id"]))
    updated_meal = await postgres_store.update_meal(
        subject,
        meal_id=int(meal["id"]),
        meal_date="2026-04-14",
        meal_label="Breakfast updated",
        notes_markdown="Updated notes",
    )
    listed_items_before = await postgres_store.list_meal_items(subject, int(meal["id"]))
    updated_manual_item = await postgres_store.update_meal_item(
        subject,
        meal_item_id=int(manual_item["id"]),
        meal_id=int(meal["id"]),
        grams=35.0,
        ingredient_name="Honey updated",
        calories=110.0,
        carbs_g=28.0,
        protein_g=0.0,
        fat_g=0.0,
    )
    deleted_manual_item = await postgres_store.delete_meal_item(
        subject,
        int(manual_item["id"]),
    )
    deleted_meal = await postgres_store.delete_meal(subject, int(meal["id"]))

    assert loaded_meal is not None and loaded_meal["meal_label"] == "Breakfast"
    assert (
        updated_meal is not None
        and updated_meal["meal_label"] == "Breakfast updated"
    )
    assert meal_item["ingredient_name"] == "Oats"
    assert meal_item["calories"] == 311.2
    assert meal_item["carbs_g"] == 52.8
    assert meal_item["protein_g"] == 13.6
    assert meal_item["fat_g"] == 5.6
    assert len(listed_items_before) == 2
    assert listed_items_before[0]["calories"] == 311.2
    assert updated_manual_item is not None
    assert updated_manual_item["ingredient_name"] == "Honey updated"
    assert updated_manual_item["grams"] == 35.0
    assert deleted_manual_item == {
        "deleted": True,
        "meal_item_id": int(manual_item["id"]),
    }
    assert deleted_meal == {"deleted": True, "meal_id": int(meal["id"])}


@pytest.mark.asyncio
async def test_postgres_store_meal_item_add_increments_product_usage_count(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure product usage count changes only for successful item additions.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("product-usage")

    product = await postgres_store.add_product(
        subject,
        name="Greek yogurt",
        default_serving_g=170.0,
        calories_per_100g=59.0,
        carbs_g_per_100g=3.6,
        protein_g_per_100g=10.0,
        fat_g_per_100g=0.4,
    )
    meal = await postgres_store.add_meal(
        subject,
        meal_date="2026-04-15",
        meal_label="Snack",
    )

    loaded_product = await postgres_store.get_product(subject, int(product["id"]))
    assert loaded_product is not None
    assert loaded_product["usage_count"] == 0

    with pytest.raises(ValueError):
        await postgres_store.add_meal_item(
            subject,
            meal_id=int(meal["id"]),
            product_id=int(product["id"]),
            grams=0.0,
        )

    loaded_after_invalid = await postgres_store.get_product(
        subject,
        int(product["id"]),
    )
    assert loaded_after_invalid is not None
    assert loaded_after_invalid["usage_count"] == 0

    first_item = await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=170.0,
    )
    loaded_after_first_add = await postgres_store.get_product(
        subject,
        int(product["id"]),
    )
    assert loaded_after_first_add is not None
    assert loaded_after_first_add["usage_count"] == 1

    await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        grams=20.0,
        ingredient_name="Honey",
        calories=61.0,
        carbs_g=17.0,
        protein_g=0.0,
        fat_g=0.0,
    )
    loaded_after_manual_add = await postgres_store.get_product(
        subject,
        int(product["id"]),
    )
    assert loaded_after_manual_add is not None
    assert loaded_after_manual_add["usage_count"] == 1

    await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=100.0,
    )
    listed_after_second_add = await postgres_store.list_products(subject)
    assert listed_after_second_add[0]["usage_count"] == 2

    await postgres_store.update_meal_item(
        subject,
        meal_item_id=int(first_item["id"]),
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=200.0,
    )
    loaded_after_update = await postgres_store.get_product(subject, int(product["id"]))
    assert loaded_after_update is not None
    assert loaded_after_update["usage_count"] == 2


@pytest.mark.asyncio
async def test_postgres_store_activities_support_json_and_external_uniqueness(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure activity entries support CRUD, JSON fields, and sync uniqueness.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("activities")
    other_subject = make_subject("activities-other")

    activity = await postgres_store.add_activity(
        subject,
        activity_date="2026-04-14",
        title="Morning ride",
        external_source="strava",
        external_activity_id="ride-1",
        athlete_id="athlete-1",
        sport_type="Ride",
        distance_meters=54000.0,
        moving_time_seconds=7200,
        elapsed_time_seconds=7600,
        total_elevation_gain_meters=850.0,
        average_speed_mps=7.5,
        max_speed_mps=15.0,
        average_heartrate=138.0,
        max_heartrate=176.0,
        average_watts=210.0,
        weighted_average_watts=225.0,
        calories=700.0,
        kilojoules=1500.0,
        suffer_score=110.0,
        trainer=False,
        commute=False,
        manual=False,
        is_private=False,
        zones={"z2": 80},
        laps=[{"lap": 1, "seconds": 600}],
        streams={"heartrate": [120, 130]},
        raw_payload={"provider": "demo"},
        notes_markdown="Imported from sync",
    )
    loaded_activity = await postgres_store.get_activity(subject, int(activity["id"]))
    listed_activities = await postgres_store.list_activities(
        subject,
        date_from="2026-04-14",
        date_to="2026-04-14",
        external_source="strava",
    )
    updated_activity = await postgres_store.update_activity(
        subject,
        activity_id=int(activity["id"]),
        activity_date="2026-04-14",
        title="Morning ride updated",
        external_source="strava",
        external_activity_id="ride-1",
        athlete_id="athlete-1",
        sport_type="Ride",
        distance_meters=55000.0,
        moving_time_seconds=7100,
        elapsed_time_seconds=7500,
        total_elevation_gain_meters=875.0,
        average_speed_mps=7.7,
        max_speed_mps=15.4,
        average_heartrate=140.0,
        max_heartrate=177.0,
        average_watts=215.0,
        weighted_average_watts=230.0,
        calories=720.0,
        kilojoules=1520.0,
        suffer_score=112.0,
        trainer=False,
        commute=False,
        manual=False,
        is_private=False,
        zones={"z2": 90},
        laps=[{"lap": 1, "seconds": 580}],
        streams={"heartrate": [122, 132]},
        raw_payload={"provider": "demo", "updated": True},
        notes_markdown="Updated from sync",
    )

    with pytest.raises(asyncpg.UniqueViolationError):
        await postgres_store.add_activity(
            subject,
            activity_date="2026-04-14",
            title="Duplicate ride",
            external_source="strava",
            external_activity_id="ride-1",
        )

    other_subject_activity = await postgres_store.add_activity(
        other_subject,
        activity_date="2026-04-14",
        title="Other user's ride",
        external_source="strava",
        external_activity_id="ride-1",
    )
    delete_result = await postgres_store.delete_activity(subject, int(activity["id"]))

    assert loaded_activity is not None
    assert loaded_activity["zones"] == {"z2": 80}
    assert listed_activities[0]["title"] == "Morning ride"
    assert updated_activity is not None
    assert updated_activity["title"] == "Morning ride updated"
    assert updated_activity["raw_payload"] == {"provider": "demo", "updated": True}
    assert other_subject_activity["title"] == "Other user's ride"
    assert delete_result == {"deleted": True, "activity_id": int(activity["id"])}


@pytest.mark.asyncio
async def test_postgres_store_upserts_external_activities_idempotently(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure external sync upserts by subject, source, and upstream id.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("external-upsert")
    other_subject = make_subject("external-upsert-other")
    activity_payload = {
        "activity_date": "2026-04-29",
        "title": "Synced run",
        "external_source": "strava",
        "external_activity_id": "activity-1",
        "athlete_id": "athlete-1",
        "sport_type": "Run",
        "distance_meters": 10000.0,
        "moving_time_seconds": 2700,
        "elapsed_time_seconds": 2800,
        "total_elevation_gain_meters": 120.0,
        "average_speed_mps": 3.7,
        "max_speed_mps": 5.2,
        "average_heartrate": 145.0,
        "max_heartrate": 178.0,
        "average_watts": None,
        "weighted_average_watts": None,
        "calories": 600.0,
        "kilojoules": None,
        "suffer_score": 80.0,
        "trainer": False,
        "commute": False,
        "manual": False,
        "is_private": False,
        "zones": {"z2": 30},
        "laps": [{"name": "Lap 1"}],
        "streams": None,
        "raw_payload": {"id": 1, "name": "Synced run"},
        "notes_markdown": "Imported from Strava.",
    }

    first_result = await postgres_store.upsert_external_activity(
        subject,
        activity_payload,
    )
    updated_payload = {
        **activity_payload,
        "title": "Synced run updated",
        "calories": 625.0,
        "raw_payload": {"id": 1, "name": "Synced run updated"},
    }
    second_result = await postgres_store.upsert_external_activity(
        subject,
        updated_payload,
    )
    other_subject_result = await postgres_store.upsert_external_activity(
        other_subject,
        activity_payload,
    )
    listed = await postgres_store.list_activities(
        subject,
        date_from="2026-04-29",
        date_to="2026-04-29",
        external_source="strava",
    )

    first_item = first_result["item"]
    second_item = second_result["item"]
    other_subject_item = other_subject_result["item"]

    assert first_result["action"] == "inserted"
    assert second_result["action"] == "updated"
    assert other_subject_result["action"] == "inserted"
    assert isinstance(first_item, dict)
    assert isinstance(second_item, dict)
    assert isinstance(other_subject_item, dict)
    assert first_item["id"] == second_item["id"]
    assert other_subject_item["id"] != first_item["id"]
    assert len(listed) == 1
    assert listed[0]["title"] == "Synced run updated"
    assert listed[0]["calories"] == 625.0


@pytest.mark.asyncio
async def test_postgres_store_external_service_tokens_are_upserted(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure external service tokens persist rotated refresh tokens.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("external-token")

    first_token = await postgres_store.save_external_service_token(
        subject=subject,
        service="strava",
        access_token="access-1",
        refresh_token="refresh-1",
        expires_at=1_776_000_000,
        raw_payload={"expires_in": 21600},
    )
    second_token = await postgres_store.save_external_service_token(
        subject=subject,
        service="strava",
        access_token="access-2",
        refresh_token="refresh-2",
        expires_at=1_776_003_600,
        raw_payload={"expires_in": 18000},
    )
    loaded_token = await postgres_store.get_external_service_token(
        subject,
        "strava",
    )

    assert first_token["refresh_token"] == "refresh-1"
    assert second_token["refresh_token"] == "refresh-2"
    assert second_token["expires_at"] == 1_776_003_600
    assert loaded_token is not None
    assert loaded_token["access_token"] == "access-2"
    assert loaded_token["refresh_token"] == "refresh-2"
    assert loaded_token["raw_payload"] == {"expires_in": 18000}


@pytest.mark.asyncio
async def test_postgres_store_memory_items_support_crud_and_scoping(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure long-term memory items support CRUD and user scoping.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("memory")
    other_subject = make_subject("memory-other")

    memory_item = await postgres_store.add_memory_item(
        subject,
        title="Fueling preference",
        content_markdown="Prefers gels after 75 minutes.",
        category="nutrition",
    )
    other_memory_item = await postgres_store.add_memory_item(
        other_subject,
        title="Other memory",
        content_markdown="Private to another subject.",
        category="private",
    )

    listed_memory = await postgres_store.list_memory_items(
        subject,
        category="nutrition",
    )
    loaded_memory = await postgres_store.get_memory_item(
        subject,
        int(memory_item["id"]),
    )
    updated_memory = await postgres_store.update_memory_item(
        subject,
        memory_item_id=int(memory_item["id"]),
        title="Fueling preference updated",
        content_markdown="Prefers gels after 60 minutes.",
        category="nutrition",
    )
    foreign_memory = await postgres_store.get_memory_item(
        subject,
        int(other_memory_item["id"]),
    )
    delete_result = await postgres_store.delete_memory_item(
        subject,
        int(memory_item["id"]),
    )

    assert listed_memory[0]["title"] == "Fueling preference"
    assert loaded_memory is not None and loaded_memory["category"] == "nutrition"
    assert updated_memory is not None
    assert updated_memory["title"] == "Fueling preference updated"
    assert foreign_memory is None
    assert delete_result == {
        "deleted": True,
        "memory_item_id": int(memory_item["id"]),
    }


@pytest.mark.asyncio
async def test_postgres_store_daily_summary_handles_empty_target_only_and_combined_days(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure daily summaries are computed from targets, meals, and activities.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject = make_subject("summary")
    product = await postgres_store.add_product(
        subject,
        name="Rice",
        default_serving_g=100.0,
        calories_per_100g=130.0,
        carbs_g_per_100g=28.0,
        protein_g_per_100g=2.4,
        fat_g_per_100g=0.3,
    )
    meal = await postgres_store.add_meal(
        subject,
        meal_date="2026-04-22",
        meal_label="Lunch",
    )
    await postgres_store.add_meal_item(
        subject,
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=200.0,
    )
    await postgres_store.add_activity(
        subject,
        activity_date="2026-04-23",
        title="Easy run",
        calories=450.0,
    )
    await postgres_store.set_daily_target(
        subject,
        target_date="2026-04-21",
        target_food_calories=2100.0,
        target_exercise_calories=400.0,
        target_protein_g=145.0,
        target_carbs_g=220.0,
        target_fat_g=55.0,
    )
    combined_meal = await postgres_store.add_meal(
        subject,
        meal_date="2026-04-24",
        meal_label="Dinner",
    )
    await postgres_store.add_meal_item(
        subject,
        meal_id=int(combined_meal["id"]),
        product_id=int(product["id"]),
        grams=150.0,
    )
    await postgres_store.add_activity(
        subject,
        activity_date="2026-04-24",
        title="Trainer ride",
        calories=600.0,
    )
    await postgres_store.set_daily_target(
        subject,
        target_date="2026-04-24",
        target_food_calories=2400.0,
        target_exercise_calories=600.0,
        target_protein_g=160.0,
        target_carbs_g=300.0,
        target_fat_g=65.0,
    )

    empty_summary = await postgres_store.get_daily_summary(subject, "2026-04-20")
    target_only_summary = await postgres_store.get_daily_summary(subject, "2026-04-21")
    meals_only_summary = await postgres_store.get_daily_summary(subject, "2026-04-22")
    activities_only_summary = await postgres_store.get_daily_summary(
        subject,
        "2026-04-23",
    )
    combined_summary = await postgres_store.get_daily_summary(subject, "2026-04-24")

    assert empty_summary == {
        "target_date": "2026-04-20",
        "target_food_calories": None,
        "target_exercise_calories": None,
        "target_protein_g": None,
        "target_carbs_g": None,
        "target_fat_g": None,
        "actual_food_calories": 0.0,
        "actual_exercise_calories": 0.0,
        "actual_protein_g": 0.0,
        "actual_carbs_g": 0.0,
        "actual_fat_g": 0.0,
        "net_calories": 0.0,
        "meals_count": 0,
        "meal_items_count": 0,
        "activities_count": 0,
    }
    assert target_only_summary["target_food_calories"] == 2100.0
    assert target_only_summary["actual_food_calories"] == 0.0
    assert meals_only_summary["actual_food_calories"] == 260.0
    assert meals_only_summary["actual_carbs_g"] == 56.0
    assert meals_only_summary["meals_count"] == 1
    assert activities_only_summary["actual_exercise_calories"] == 450.0
    assert activities_only_summary["activities_count"] == 1
    assert combined_summary["target_food_calories"] == 2400.0
    assert combined_summary["actual_food_calories"] == 195.0
    assert combined_summary["actual_exercise_calories"] == 600.0
    assert combined_summary["net_calories"] == -405.0


@pytest.mark.asyncio
async def test_postgres_store_subject_scoping_hides_other_users_rows(
    postgres_store: PostgresUserStore,
) -> None:
    """Ensure subject filtering prevents one user from reading another's rows.

    Parameters:
        postgres_store: Connected Postgres user store.

    Returns:
        None.
    """

    subject_a = make_subject("scope-a")
    subject_b = make_subject("scope-b")

    product = await postgres_store.add_product(
        subject_a,
        name="Banana",
        default_serving_g=120.0,
        calories_per_100g=89.0,
        carbs_g_per_100g=23.0,
        protein_g_per_100g=1.1,
        fat_g_per_100g=0.3,
    )
    meal = await postgres_store.add_meal(
        subject_a,
        meal_date="2026-04-14",
        meal_label="Snack",
    )
    meal_item = await postgres_store.add_meal_item(
        subject_a,
        meal_id=int(meal["id"]),
        product_id=int(product["id"]),
        grams=120.0,
    )
    activity = await postgres_store.add_activity(
        subject_a,
        activity_date="2026-04-14",
        title="Walk",
        calories=150.0,
    )
    memory_item = await postgres_store.add_memory_item(
        subject_a,
        title="Bananas work well pre-run",
        content_markdown="Easy on the stomach.",
    )
    await postgres_store.set_daily_target(
        subject_a,
        target_date="2026-04-14",
        target_food_calories=2000.0,
        target_exercise_calories=300.0,
        target_protein_g=140.0,
        target_carbs_g=240.0,
        target_fat_g=55.0,
    )
    await postgres_store.set_daily_metric(
        subject_a,
        metric_date="2026-04-14",
        metric_type="weight",
        value=70.0,
    )

    assert await postgres_store.get_product(subject_b, int(product["id"])) is None
    assert await postgres_store.get_meal(subject_b, int(meal["id"])) is None
    meal_items = await postgres_store.list_meal_items(subject_a, int(meal["id"]))
    assert meal_items[0]["id"] == meal_item["id"]
    assert await postgres_store.get_activity(subject_b, int(activity["id"])) is None
    assert (
        await postgres_store.get_memory_item(subject_b, int(memory_item["id"]))
        is None
    )
    assert await postgres_store.get_daily_target(subject_b, "2026-04-14") is None
    assert (
        await postgres_store.get_daily_metric(subject_b, "2026-04-14", "weight")
        is None
    )
    assert await postgres_store.list_products(subject_b) == []
    assert await postgres_store.list_activities(subject_b) == []
    assert await postgres_store.list_daily_metrics(subject_b) == []
    assert await postgres_store.list_memory_items(subject_b) == []


@pytest.mark.asyncio
async def test_postgres_store_disables_statement_cache_for_pooler_compatibility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure asyncpg pool creation stays compatible with Supabase poolers.

    Parameters:
        monkeypatch: Pytest helper used to patch `asyncpg.create_pool`.

    Returns:
        None.
    """

    captured_kwargs: dict[str, object] = {}

    async def fake_create_pool(**kwargs: object) -> _FakePool:
        """Capture asyncpg pool options while returning a fake pool.

        Parameters:
            **kwargs: Pool options forwarded by `PostgresUserStore`.

        Returns:
            _FakePool: Pool stub used by `_ensure_pool()`.
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
