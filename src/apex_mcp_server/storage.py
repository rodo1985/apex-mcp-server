"""Postgres-backed storage for the FastMCP wellness pilot."""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from datetime import date, datetime
from math import isfinite
from typing import Any

import asyncpg

from apex_mcp_server.config import Settings
from apex_mcp_server.models import ProfileSaveResult, UserData, UserDataSaveResult

DAILY_METRIC_TYPES = frozenset({"weight", "steps", "sleep_hours"})

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

ALTER TABLE user_profiles
    ADD COLUMN IF NOT EXISTS diet_preferences_markdown TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS diet_goals_markdown TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS training_goals_markdown TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS food_products (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    name TEXT NOT NULL,
    default_serving_g DOUBLE PRECISION,
    calories_per_100g DOUBLE PRECISION NOT NULL,
    carbs_g_per_100g DOUBLE PRECISION NOT NULL,
    protein_g_per_100g DOUBLE PRECISION NOT NULL,
    fat_g_per_100g DOUBLE PRECISION NOT NULL,
    usage_count INTEGER NOT NULL DEFAULT 0,
    notes_markdown TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subject, name)
);

ALTER TABLE food_products
    ADD COLUMN IF NOT EXISTS usage_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_food_products_subject_name
    ON food_products (subject, name);

CREATE TABLE IF NOT EXISTS daily_targets (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    target_date DATE NOT NULL,
    target_food_calories DOUBLE PRECISION NOT NULL,
    target_exercise_calories DOUBLE PRECISION NOT NULL,
    target_protein_g DOUBLE PRECISION NOT NULL,
    target_carbs_g DOUBLE PRECISION NOT NULL,
    target_fat_g DOUBLE PRECISION NOT NULL,
    notes_markdown TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subject, target_date)
);

CREATE INDEX IF NOT EXISTS idx_daily_targets_subject_date
    ON daily_targets (subject, target_date);

CREATE TABLE IF NOT EXISTS daily_metrics (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    metric_date DATE NOT NULL,
    metric_type TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subject, metric_date, metric_type)
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_subject_type_date
    ON daily_metrics (subject, metric_type, metric_date DESC);

CREATE TABLE IF NOT EXISTS daily_meals (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    meal_date DATE NOT NULL,
    meal_label TEXT NOT NULL,
    notes_markdown TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_meals_subject_date
    ON daily_meals (subject, meal_date);

CREATE TABLE IF NOT EXISTS meal_items (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    meal_id BIGINT NOT NULL REFERENCES daily_meals(id) ON DELETE CASCADE,
    product_id BIGINT REFERENCES food_products(id) ON DELETE SET NULL,
    ingredient_name TEXT NOT NULL,
    grams DOUBLE PRECISION NOT NULL,
    calories DOUBLE PRECISION NOT NULL,
    carbs_g DOUBLE PRECISION NOT NULL,
    protein_g DOUBLE PRECISION NOT NULL,
    fat_g DOUBLE PRECISION NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_meal_items_subject_meal
    ON meal_items (subject, meal_id);

CREATE TABLE IF NOT EXISTS activity_entries (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    activity_date DATE NOT NULL,
    title TEXT NOT NULL,
    external_source TEXT,
    external_activity_id TEXT,
    athlete_id TEXT,
    sport_type TEXT,
    distance_meters DOUBLE PRECISION,
    moving_time_seconds INTEGER,
    elapsed_time_seconds INTEGER,
    total_elevation_gain_meters DOUBLE PRECISION,
    average_speed_mps DOUBLE PRECISION,
    max_speed_mps DOUBLE PRECISION,
    average_heartrate DOUBLE PRECISION,
    max_heartrate DOUBLE PRECISION,
    average_watts DOUBLE PRECISION,
    weighted_average_watts DOUBLE PRECISION,
    calories DOUBLE PRECISION,
    kilojoules DOUBLE PRECISION,
    suffer_score DOUBLE PRECISION,
    trainer BOOLEAN NOT NULL DEFAULT FALSE,
    commute BOOLEAN NOT NULL DEFAULT FALSE,
    manual BOOLEAN NOT NULL DEFAULT TRUE,
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    zones JSONB,
    laps JSONB,
    streams JSONB,
    raw_payload JSONB,
    notes_markdown TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_activity_entries_subject_date
    ON activity_entries (subject, activity_date);

CREATE UNIQUE INDEX IF NOT EXISTS uniq_activity_entries_external
    ON activity_entries (subject, external_source, external_activity_id)
    WHERE external_source IS NOT NULL AND external_activity_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS memory_items (
    id BIGSERIAL PRIMARY KEY,
    subject TEXT NOT NULL,
    title TEXT NOT NULL,
    category TEXT,
    content_markdown TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_items_subject_created
    ON memory_items (subject, created_at DESC);
""".strip()

_DOCUMENT_COLUMNS = {
    "profile_markdown",
    "diet_preferences_markdown",
    "diet_goals_markdown",
    "training_goals_markdown",
}

_JSON_COLUMNS = {
    "zones",
    "laps",
    "streams",
    "raw_payload",
}


class UserStore(ABC):
    """Define the persisted wellness-data contract used by the MCP server.

    Parameters:
        None.

    Returns:
        UserStore: Abstract storage interface implemented by the Postgres
            backend and test doubles.

    Raises:
        This abstract base class does not raise errors directly.
    """

    @abstractmethod
    async def get_profile(self, subject: str) -> str:
        """Read the saved profile markdown for a subject."""

    @abstractmethod
    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the saved profile markdown for a subject."""

    @abstractmethod
    async def get_user_data(self, subject: str) -> UserData:
        """Read the saved numeric user data for a subject."""

    @abstractmethod
    async def set_user_data(
        self,
        subject: str,
        data: UserData,
        login: str | None = None,
    ) -> UserDataSaveResult:
        """Overwrite the saved numeric user data for a subject."""

    @abstractmethod
    async def get_diet_preferences(self, subject: str) -> str:
        """Read the saved diet-preferences markdown for a subject."""

    @abstractmethod
    async def set_diet_preferences(
        self,
        subject: str,
        diet_preferences_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the saved diet-preferences markdown for a subject."""

    @abstractmethod
    async def get_diet_goals(self, subject: str) -> str:
        """Read the saved diet-goals markdown for a subject."""

    @abstractmethod
    async def set_diet_goals(
        self,
        subject: str,
        diet_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the saved diet-goals markdown for a subject."""

    @abstractmethod
    async def get_training_goals(self, subject: str) -> str:
        """Read the saved training-goals markdown for a subject."""

    @abstractmethod
    async def set_training_goals(
        self,
        subject: str,
        training_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the saved training-goals markdown for a subject."""

    @abstractmethod
    async def list_products(self, subject: str) -> list[dict[str, object]]:
        """List all food products owned by a subject."""

    @abstractmethod
    async def get_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object] | None:
        """Read one food product owned by a subject."""

    @abstractmethod
    async def add_product(
        self,
        subject: str,
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create a new food product for a subject."""

    @abstractmethod
    async def update_product(
        self,
        subject: str,
        product_id: int,
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one food product owned by a subject."""

    @abstractmethod
    async def delete_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object]:
        """Delete one food product owned by a subject."""

    @abstractmethod
    async def list_daily_targets(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily targets for a subject, optionally within a date range."""

    @abstractmethod
    async def get_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object] | None:
        """Read one daily target row for a subject and date."""

    @abstractmethod
    async def set_daily_target(
        self,
        subject: str,
        target_date: str,
        target_food_calories: float,
        target_exercise_calories: float,
        target_protein_g: float,
        target_carbs_g: float,
        target_fat_g: float,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Upsert one daily target row for a subject and date."""

    @abstractmethod
    async def delete_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Delete one daily target row for a subject and date."""

    @abstractmethod
    async def list_daily_metrics(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        metric_type: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily metric rows for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            metric_type: Optional supported metric type filter.

        Returns:
            list[dict[str, object]]: Metric rows visible to the subject.

        Raises:
            ValueError: If a provided filter is invalid.
            Exception: Propagated from the concrete storage backend.
        """

    @abstractmethod
    async def get_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
    ) -> dict[str, object] | None:
        """Read one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the requested metric.
            metric_type: Supported metric type to read.

        Returns:
            dict[str, object] | None: Metric row, or `None` when missing.

        Raises:
            ValueError: If the date or metric type is invalid.
            Exception: Propagated from the concrete storage backend.
        """

    @abstractmethod
    async def set_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
        value: float,
    ) -> dict[str, object]:
        """Upsert one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric.
            metric_type: Supported metric type to store.
            value: Numeric metric value validated by metric type.

        Returns:
            dict[str, object]: Upserted metric row.

        Raises:
            ValueError: If the date, metric type, or value is invalid.
            Exception: Propagated from the concrete storage backend.
        """

    @abstractmethod
    async def delete_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
    ) -> dict[str, object]:
        """Delete one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric row.
            metric_type: Supported metric type to delete.

        Returns:
            dict[str, object]: Deletion metadata.

        Raises:
            ValueError: If the date or metric type is invalid.
            Exception: Propagated from the concrete storage backend.
        """

    @abstractmethod
    async def list_daily_meals(
        self,
        subject: str,
        meal_date: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily meals for a subject, optionally scoped to one day."""

    @abstractmethod
    async def get_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object] | None:
        """Read one meal header owned by a subject."""

    @abstractmethod
    async def add_meal(
        self,
        subject: str,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create a meal header for a subject."""

    @abstractmethod
    async def update_meal(
        self,
        subject: str,
        meal_id: int,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one meal header owned by a subject."""

    @abstractmethod
    async def delete_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object]:
        """Delete one meal header owned by a subject."""

    @abstractmethod
    async def list_meal_items(
        self,
        subject: str,
        meal_id: int,
    ) -> list[dict[str, object]]:
        """List all meal items for one meal owned by a subject."""

    @abstractmethod
    async def add_meal_item(
        self,
        subject: str,
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
    ) -> dict[str, object]:
        """Create one meal item owned by a subject."""

    @abstractmethod
    async def update_meal_item(
        self,
        subject: str,
        meal_item_id: int,
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
    ) -> dict[str, object] | None:
        """Replace one meal item owned by a subject."""

    @abstractmethod
    async def delete_meal_item(
        self,
        subject: str,
        meal_item_id: int,
    ) -> dict[str, object]:
        """Delete one meal item owned by a subject."""

    @abstractmethod
    async def list_activities(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        external_source: str | None = None,
    ) -> list[dict[str, object]]:
        """List activity entries for a subject."""

    @abstractmethod
    async def get_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object] | None:
        """Read one activity entry owned by a subject."""

    @abstractmethod
    async def add_activity(
        self,
        subject: str,
        activity_date: str,
        title: str,
        external_source: str | None = None,
        external_activity_id: str | None = None,
        athlete_id: str | None = None,
        sport_type: str | None = None,
        distance_meters: float | None = None,
        moving_time_seconds: int | None = None,
        elapsed_time_seconds: int | None = None,
        total_elevation_gain_meters: float | None = None,
        average_speed_mps: float | None = None,
        max_speed_mps: float | None = None,
        average_heartrate: float | None = None,
        max_heartrate: float | None = None,
        average_watts: float | None = None,
        weighted_average_watts: float | None = None,
        calories: float | None = None,
        kilojoules: float | None = None,
        suffer_score: float | None = None,
        trainer: bool = False,
        commute: bool = False,
        manual: bool = True,
        is_private: bool = False,
        zones: dict[str, object] | None = None,
        laps: list[dict[str, object]] | None = None,
        streams: dict[str, object] | None = None,
        raw_payload: dict[str, object] | None = None,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create one activity entry for a subject."""

    @abstractmethod
    async def update_activity(
        self,
        subject: str,
        activity_id: int,
        activity_date: str,
        title: str,
        external_source: str | None = None,
        external_activity_id: str | None = None,
        athlete_id: str | None = None,
        sport_type: str | None = None,
        distance_meters: float | None = None,
        moving_time_seconds: int | None = None,
        elapsed_time_seconds: int | None = None,
        total_elevation_gain_meters: float | None = None,
        average_speed_mps: float | None = None,
        max_speed_mps: float | None = None,
        average_heartrate: float | None = None,
        max_heartrate: float | None = None,
        average_watts: float | None = None,
        weighted_average_watts: float | None = None,
        calories: float | None = None,
        kilojoules: float | None = None,
        suffer_score: float | None = None,
        trainer: bool = False,
        commute: bool = False,
        manual: bool = True,
        is_private: bool = False,
        zones: dict[str, object] | None = None,
        laps: list[dict[str, object]] | None = None,
        streams: dict[str, object] | None = None,
        raw_payload: dict[str, object] | None = None,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one activity entry owned by a subject."""

    @abstractmethod
    async def upsert_external_activity(
        self,
        subject: str,
        activity: dict[str, object],
    ) -> dict[str, object]:
        """Insert or update one externally sourced activity row.

        Parameters:
            subject: Stable row owner for the current caller.
            activity: Activity payload with `external_source` and
                `external_activity_id` populated by an external sync service.

        Returns:
            dict[str, object]: Upsert result with `action` and `item` keys.

        Raises:
            ValueError: If required external identifiers are missing.
            Exception: Propagated from the concrete storage backend.
        """

    @abstractmethod
    async def delete_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object]:
        """Delete one activity entry owned by a subject."""

    @abstractmethod
    async def list_memory_items(
        self,
        subject: str,
        category: str | None = None,
    ) -> list[dict[str, object]]:
        """List long-term memory items for a subject."""

    @abstractmethod
    async def get_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object] | None:
        """Read one long-term memory item owned by a subject."""

    @abstractmethod
    async def add_memory_item(
        self,
        subject: str,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object]:
        """Create one long-term memory item for a subject."""

    @abstractmethod
    async def update_memory_item(
        self,
        subject: str,
        memory_item_id: int,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object] | None:
        """Replace one long-term memory item owned by a subject."""

    @abstractmethod
    async def delete_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object]:
        """Delete one long-term memory item owned by a subject."""

    @abstractmethod
    async def get_daily_summary(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Compute the daily target-vs-actual summary for one date."""

    @abstractmethod
    async def close(self) -> None:
        """Release any backend resources such as database pools."""


class PostgresUserStore(UserStore):
    """Persist wellness data in Postgres using a straightforward SQL layer.

    Parameters:
        database_url: Async Postgres connection string.
        schema_sql: SQL used to bootstrap the current baseline schema.

    Returns:
        PostgresUserStore: Postgres storage backend used by the MCP server.

    Raises:
        Exception: The underlying asyncpg driver may raise connection or query
            errors.

    Example:
        >>> store = PostgresUserStore("postgresql://demo:demo@localhost:5432/demo")
        >>> store.database_url.startswith("postgresql://")
        True
    """

    def __init__(self, database_url: str, schema_sql: str = SCHEMA_SQL) -> None:
        """Store connection settings and bootstrap SQL for first use.

        Parameters:
            database_url: Async Postgres connection string.
            schema_sql: SQL used to create or evolve the baseline schema.

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
        """Read the profile markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            str: Stored markdown, or an empty string when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        return await self._get_markdown_document(subject, "profile_markdown")

    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the profile markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            profile_markdown: New markdown content for the profile.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Save confirmation used by the MCP tool.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._upsert_user_profile_fields(
            subject,
            login=login,
            fields={"profile_markdown": profile_markdown},
        )
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(profile_markdown.encode("utf-8")),
        )

    async def get_user_data(self, subject: str) -> UserData:
        """Read the numeric user data stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            UserData: Numeric body metrics, or all-null values when missing.

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
            subject: Stable row owner for the current caller.
            data: Numeric values to persist.
            login: Optional friendly login captured from the auth layer.

        Returns:
            UserDataSaveResult: Save confirmation used by the MCP tool.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._upsert_user_profile_fields(
            subject,
            login=login,
            fields={
                "weight_kg": data.weight_kg,
                "height_cm": data.height_cm,
                "ftp_watts": data.ftp_watts,
            },
        )
        return UserDataSaveResult(
            saved=True,
            subject=subject,
            weight_kg=data.weight_kg,
            height_cm=data.height_cm,
            ftp_watts=data.ftp_watts,
        )

    async def get_diet_preferences(self, subject: str) -> str:
        """Read the diet-preferences markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            str: Stored markdown, or an empty string when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        return await self._get_markdown_document(
            subject,
            "diet_preferences_markdown",
        )

    async def set_diet_preferences(
        self,
        subject: str,
        diet_preferences_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the diet-preferences markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            diet_preferences_markdown: New markdown content.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Save confirmation used by the MCP tool.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._upsert_user_profile_fields(
            subject,
            login=login,
            fields={"diet_preferences_markdown": diet_preferences_markdown},
        )
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(diet_preferences_markdown.encode("utf-8")),
        )

    async def get_diet_goals(self, subject: str) -> str:
        """Read the diet-goals markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            str: Stored markdown, or an empty string when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        return await self._get_markdown_document(subject, "diet_goals_markdown")

    async def set_diet_goals(
        self,
        subject: str,
        diet_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the diet-goals markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            diet_goals_markdown: New markdown content.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Save confirmation used by the MCP tool.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._upsert_user_profile_fields(
            subject,
            login=login,
            fields={"diet_goals_markdown": diet_goals_markdown},
        )
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(diet_goals_markdown.encode("utf-8")),
        )

    async def get_training_goals(self, subject: str) -> str:
        """Read the training-goals markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            str: Stored markdown, or an empty string when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        return await self._get_markdown_document(subject, "training_goals_markdown")

    async def set_training_goals(
        self,
        subject: str,
        training_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Overwrite the training-goals markdown stored for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            training_goals_markdown: New markdown content.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Save confirmation used by the MCP tool.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        await self._upsert_user_profile_fields(
            subject,
            login=login,
            fields={"training_goals_markdown": training_goals_markdown},
        )
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(training_goals_markdown.encode("utf-8")),
        )

    async def list_products(self, subject: str) -> list[dict[str, object]]:
        """List all food products owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            list[dict[str, object]]: Product records ordered by name.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        rows = await self._fetch(
            """
            SELECT id, subject, name, default_serving_g, calories_per_100g,
                   carbs_g_per_100g, protein_g_per_100g, fat_g_per_100g,
                   COALESCE(usage_count, 0)::INTEGER AS usage_count,
                   notes_markdown, created_at, updated_at
            FROM food_products
            WHERE subject = $1
            ORDER BY LOWER(name), id
            """,
            subject,
        )
        return self._rows_to_dicts(rows)

    async def get_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object] | None:
        """Read one food product owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Product identifier within the subject's catalog.

        Returns:
            dict[str, object] | None: Product record, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT id, subject, name, default_serving_g, calories_per_100g,
                   carbs_g_per_100g, protein_g_per_100g, fat_g_per_100g,
                   COALESCE(usage_count, 0)::INTEGER AS usage_count,
                   notes_markdown, created_at, updated_at
            FROM food_products
            WHERE subject = $1 AND id = $2
            """,
            subject,
            product_id,
        )
        return self._row_to_dict(row)

    async def add_product(
        self,
        subject: str,
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create one food product in the subject-private catalog.

        Parameters:
            subject: Stable row owner for the current caller.
            name: Display name of the product.
            default_serving_g: Optional common serving size in grams.
            calories_per_100g: Calories per 100 grams.
            carbs_g_per_100g: Carbohydrates per 100 grams.
            protein_g_per_100g: Protein per 100 grams.
            fat_g_per_100g: Fat per 100 grams.
            notes_markdown: Optional freeform product notes.

        Returns:
            dict[str, object]: Newly created product row.

        Raises:
            Exception: Propagated from asyncpg when the insert fails.
        """

        row = await self._fetchrow(
            """
            INSERT INTO food_products (
                subject, name, default_serving_g, calories_per_100g,
                carbs_g_per_100g, protein_g_per_100g, fat_g_per_100g,
                notes_markdown
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id, subject, name, default_serving_g, calories_per_100g,
                      carbs_g_per_100g, protein_g_per_100g, fat_g_per_100g,
                      COALESCE(usage_count, 0)::INTEGER AS usage_count,
                      notes_markdown, created_at, updated_at
            """,
            subject,
            name,
            default_serving_g,
            calories_per_100g,
            carbs_g_per_100g,
            protein_g_per_100g,
            fat_g_per_100g,
            notes_markdown,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for food_products.",
        )

    async def update_product(
        self,
        subject: str,
        product_id: int,
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one food product owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Product identifier within the subject's catalog.
            name: Updated display name.
            default_serving_g: Updated optional serving size.
            calories_per_100g: Updated calories per 100 grams.
            carbs_g_per_100g: Updated carbohydrates per 100 grams.
            protein_g_per_100g: Updated protein per 100 grams.
            fat_g_per_100g: Updated fat per 100 grams.
            notes_markdown: Updated freeform notes.

        Returns:
            dict[str, object] | None: Updated product row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the update fails.
        """

        row = await self._fetchrow(
            """
            UPDATE food_products
            SET
                name = $3,
                default_serving_g = $4,
                calories_per_100g = $5,
                carbs_g_per_100g = $6,
                protein_g_per_100g = $7,
                fat_g_per_100g = $8,
                notes_markdown = $9,
                updated_at = NOW()
            WHERE subject = $1 AND id = $2
            RETURNING id, subject, name, default_serving_g, calories_per_100g,
                      carbs_g_per_100g, protein_g_per_100g, fat_g_per_100g,
                      COALESCE(usage_count, 0)::INTEGER AS usage_count,
                      notes_markdown, created_at, updated_at
            """,
            subject,
            product_id,
            name,
            default_serving_g,
            calories_per_100g,
            carbs_g_per_100g,
            protein_g_per_100g,
            fat_g_per_100g,
            notes_markdown,
        )
        return self._row_to_dict(row)

    async def delete_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object]:
        """Delete one food product owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Product identifier within the subject's catalog.

        Returns:
            dict[str, object]: Deletion result with a boolean flag.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        command = await self._execute(
            "DELETE FROM food_products WHERE subject = $1 AND id = $2",
            subject,
            product_id,
        )
        return {"deleted": command != "DELETE 0", "product_id": product_id}

    async def list_daily_targets(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily target rows for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.

        Returns:
            list[dict[str, object]]: Daily targets ordered by date.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        filters = ["subject = $1"]
        args: list[object] = [subject]

        if date_from is not None:
            args.append(_parse_iso_date(date_from))
            filters.append(f"target_date >= ${len(args)}")

        if date_to is not None:
            args.append(_parse_iso_date(date_to))
            filters.append(f"target_date <= ${len(args)}")

        rows = await self._fetch(
            f"""
            SELECT id, subject, target_date, target_food_calories,
                   target_exercise_calories, target_protein_g, target_carbs_g,
                   target_fat_g, notes_markdown, created_at, updated_at
            FROM daily_targets
            WHERE {' AND '.join(filters)}
            ORDER BY target_date DESC, id DESC
            """,
            *args,
        )
        return self._rows_to_dicts(rows)

    async def get_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object] | None:
        """Read one daily target row for a subject and date.

        Parameters:
            subject: Stable row owner for the current caller.
            target_date: ISO calendar date for the requested target.

        Returns:
            dict[str, object] | None: Daily target row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT id, subject, target_date, target_food_calories,
                   target_exercise_calories, target_protein_g, target_carbs_g,
                   target_fat_g, notes_markdown, created_at, updated_at
            FROM daily_targets
            WHERE subject = $1 AND target_date = $2
            """,
            subject,
            _parse_iso_date(target_date),
        )
        return self._row_to_dict(row)

    async def set_daily_target(
        self,
        subject: str,
        target_date: str,
        target_food_calories: float,
        target_exercise_calories: float,
        target_protein_g: float,
        target_carbs_g: float,
        target_fat_g: float,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Upsert one daily target row for a subject and date.

        Parameters:
            subject: Stable row owner for the current caller.
            target_date: ISO calendar date for the target row.
            target_food_calories: Target calories from food.
            target_exercise_calories: Target calories expected from exercise.
            target_protein_g: Target grams of protein.
            target_carbs_g: Target grams of carbohydrates.
            target_fat_g: Target grams of fat.
            notes_markdown: Optional freeform notes for the day.

        Returns:
            dict[str, object]: Upserted daily target row.

        Raises:
            Exception: Propagated from asyncpg when the upsert fails.
        """

        row = await self._fetchrow(
            """
            INSERT INTO daily_targets (
                subject, target_date, target_food_calories,
                target_exercise_calories, target_protein_g, target_carbs_g,
                target_fat_g, notes_markdown
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (subject, target_date) DO UPDATE
            SET
                target_food_calories = EXCLUDED.target_food_calories,
                target_exercise_calories = EXCLUDED.target_exercise_calories,
                target_protein_g = EXCLUDED.target_protein_g,
                target_carbs_g = EXCLUDED.target_carbs_g,
                target_fat_g = EXCLUDED.target_fat_g,
                notes_markdown = EXCLUDED.notes_markdown,
                updated_at = NOW()
            RETURNING id, subject, target_date, target_food_calories,
                      target_exercise_calories, target_protein_g,
                      target_carbs_g, target_fat_g, notes_markdown,
                      created_at, updated_at
            """,
            subject,
            _parse_iso_date(target_date),
            target_food_calories,
            target_exercise_calories,
            target_protein_g,
            target_carbs_g,
            target_fat_g,
            notes_markdown,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for daily_targets.",
        )

    async def delete_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Delete one daily target row for a subject and date.

        Parameters:
            subject: Stable row owner for the current caller.
            target_date: ISO calendar date for the target row.

        Returns:
            dict[str, object]: Deletion result with the target date.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        parsed_date = _parse_iso_date(target_date)
        command = await self._execute(
            "DELETE FROM daily_targets WHERE subject = $1 AND target_date = $2",
            subject,
            parsed_date,
        )
        return {
            "deleted": command != "DELETE 0",
            "target_date": parsed_date.isoformat(),
        }

    async def list_daily_metrics(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        metric_type: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily metric rows for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            metric_type: Optional supported metric type filter.

        Returns:
            list[dict[str, object]]: Metric rows ordered for trend reading.

        Raises:
            ValueError: If `metric_type` or date filters are invalid.
            Exception: Propagated from asyncpg when the query fails.
        """

        filters = ["subject = $1"]
        args: list[object] = [subject]

        if date_from is not None:
            args.append(_parse_iso_date(date_from))
            filters.append(f"metric_date >= ${len(args)}")

        if date_to is not None:
            args.append(_parse_iso_date(date_to))
            filters.append(f"metric_date <= ${len(args)}")

        if metric_type is not None:
            args.append(_normalize_daily_metric_type(metric_type))
            filters.append(f"metric_type = ${len(args)}")

        rows = await self._fetch(
            f"""
            SELECT id, subject, metric_date, metric_type, value,
                   created_at, updated_at
            FROM daily_metrics
            WHERE {' AND '.join(filters)}
            ORDER BY metric_date DESC, metric_type, id DESC
            """,
            *args,
        )
        return self._rows_to_dicts(rows)

    async def get_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
    ) -> dict[str, object] | None:
        """Read one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric.
            metric_type: Supported metric type such as `weight`.

        Returns:
            dict[str, object] | None: Daily metric row, or `None` when missing.

        Raises:
            ValueError: If the date or metric type is invalid.
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT id, subject, metric_date, metric_type, value,
                   created_at, updated_at
            FROM daily_metrics
            WHERE subject = $1 AND metric_date = $2 AND metric_type = $3
            """,
            subject,
            _parse_iso_date(metric_date),
            _normalize_daily_metric_type(metric_type),
        )
        return self._row_to_dict(row)

    async def set_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
        value: float,
    ) -> dict[str, object]:
        """Upsert one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric.
            metric_type: Supported metric type such as `steps`.
            value: Numeric metric value validated for the requested type.

        Returns:
            dict[str, object]: Upserted daily metric row.

        Raises:
            ValueError: If the date, metric type, or value is invalid.
            Exception: Propagated from asyncpg when the upsert fails.
        """

        normalized_type = _normalize_daily_metric_type(metric_type)
        normalized_value = _validate_daily_metric_value(normalized_type, value)

        row = await self._fetchrow(
            """
            INSERT INTO daily_metrics (subject, metric_date, metric_type, value)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (subject, metric_date, metric_type) DO UPDATE
            SET
                value = EXCLUDED.value,
                updated_at = NOW()
            RETURNING id, subject, metric_date, metric_type, value,
                      created_at, updated_at
            """,
            subject,
            _parse_iso_date(metric_date),
            normalized_type,
            normalized_value,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for daily_metrics.",
        )

    async def delete_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
    ) -> dict[str, object]:
        """Delete one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric row.
            metric_type: Supported metric type to delete.

        Returns:
            dict[str, object]: Deletion result with date and metric type.

        Raises:
            ValueError: If the date or metric type is invalid.
            Exception: Propagated from asyncpg when the delete fails.
        """

        parsed_date = _parse_iso_date(metric_date)
        normalized_type = _normalize_daily_metric_type(metric_type)
        command = await self._execute(
            """
            DELETE FROM daily_metrics
            WHERE subject = $1 AND metric_date = $2 AND metric_type = $3
            """,
            subject,
            parsed_date,
            normalized_type,
        )
        return {
            "deleted": command != "DELETE 0",
            "metric_date": parsed_date.isoformat(),
            "metric_type": normalized_type,
        }

    async def list_daily_meals(
        self,
        subject: str,
        meal_date: str | None = None,
    ) -> list[dict[str, object]]:
        """List meal headers for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_date: Optional ISO date to limit the result to one day.

        Returns:
            list[dict[str, object]]: Meal header rows ordered by date and id.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        if meal_date is None:
            rows = await self._fetch(
                """
                SELECT id, subject, meal_date, meal_label, notes_markdown,
                       created_at, updated_at
                FROM daily_meals
                WHERE subject = $1
                ORDER BY meal_date DESC, id DESC
                """,
                subject,
            )
            return self._rows_to_dicts(rows)

        rows = await self._fetch(
            """
            SELECT id, subject, meal_date, meal_label, notes_markdown,
                   created_at, updated_at
            FROM daily_meals
            WHERE subject = $1 AND meal_date = $2
            ORDER BY id
            """,
            subject,
            _parse_iso_date(meal_date),
        )
        return self._rows_to_dicts(rows)

    async def get_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object] | None:
        """Read one meal header owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier to fetch.

        Returns:
            dict[str, object] | None: Meal row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetch_meal(subject, meal_id)
        return self._row_to_dict(row)

    async def add_meal(
        self,
        subject: str,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create one meal header for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_date: ISO calendar date for the meal.
            meal_label: Free-text meal label such as lunch or post-workout.
            notes_markdown: Optional meal-level notes.

        Returns:
            dict[str, object]: Newly created meal row.

        Raises:
            Exception: Propagated from asyncpg when the insert fails.
        """

        row = await self._fetchrow(
            """
            INSERT INTO daily_meals (subject, meal_date, meal_label, notes_markdown)
            VALUES ($1, $2, $3, $4)
            RETURNING id, subject, meal_date, meal_label, notes_markdown,
                      created_at, updated_at
            """,
            subject,
            _parse_iso_date(meal_date),
            meal_label,
            notes_markdown,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for daily_meals.",
        )

    async def update_meal(
        self,
        subject: str,
        meal_id: int,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one meal header owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier to update.
            meal_date: Replacement ISO calendar date.
            meal_label: Replacement free-text meal label.
            notes_markdown: Replacement meal notes.

        Returns:
            dict[str, object] | None: Updated meal row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the update fails.
        """

        row = await self._fetchrow(
            """
            UPDATE daily_meals
            SET
                meal_date = $3,
                meal_label = $4,
                notes_markdown = $5,
                updated_at = NOW()
            WHERE subject = $1 AND id = $2
            RETURNING id, subject, meal_date, meal_label, notes_markdown,
                      created_at, updated_at
            """,
            subject,
            meal_id,
            _parse_iso_date(meal_date),
            meal_label,
            notes_markdown,
        )
        return self._row_to_dict(row)

    async def delete_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object]:
        """Delete one meal header owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier to delete.

        Returns:
            dict[str, object]: Deletion result with the meal id.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        command = await self._execute(
            "DELETE FROM daily_meals WHERE subject = $1 AND id = $2",
            subject,
            meal_id,
        )
        return {"deleted": command != "DELETE 0", "meal_id": meal_id}

    async def list_meal_items(
        self,
        subject: str,
        meal_id: int,
    ) -> list[dict[str, object]]:
        """List all meal items attached to one subject-owned meal.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Parent meal identifier.

        Returns:
            list[dict[str, object]]: Meal item rows ordered by id.

        Raises:
            RuntimeError: If the parent meal does not belong to the subject.
            Exception: Propagated from asyncpg when the query fails.
        """

        await self._require_meal(subject, meal_id)
        rows = await self._fetch(
            """
            SELECT id, subject, meal_id, product_id, ingredient_name, grams,
                   calories, carbs_g, protein_g, fat_g, created_at, updated_at
            FROM meal_items
            WHERE subject = $1 AND meal_id = $2
            ORDER BY id
            """,
            subject,
            meal_id,
        )
        return self._rows_to_dicts(rows)

    async def add_meal_item(
        self,
        subject: str,
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
    ) -> dict[str, object]:
        """Create one meal item with either a product snapshot or manual macros.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Parent meal identifier.
            grams: Consumed grams for the meal item.
            ingredient_name: Free-text ingredient name for manual items or
                optional custom label for catalog-based items.
            product_id: Optional catalog product identifier used to compute the
                nutrition snapshot.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.

        Returns:
            dict[str, object]: Newly created meal item row. Product-backed
                additions also increment the referenced product's internal
                `usage_count` in the same transaction.

        Raises:
            RuntimeError: If the meal or referenced product is invalid.
            ValueError: If manual nutrient values are incomplete.
            Exception: Propagated from asyncpg when the insert fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            async with connection.transaction():
                await self._require_meal(subject, meal_id, connection=connection)
                snapshot = await self._build_meal_item_snapshot(
                    subject=subject,
                    product_id=product_id,
                    ingredient_name=ingredient_name,
                    grams=grams,
                    calories=calories,
                    carbs_g=carbs_g,
                    protein_g=protein_g,
                    fat_g=fat_g,
                    connection=connection,
                )

                row = await connection.fetchrow(
                    """
                    INSERT INTO meal_items (
                        subject, meal_id, product_id, ingredient_name, grams,
                        calories, carbs_g, protein_g, fat_g
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id, subject, meal_id, product_id, ingredient_name, grams,
                              calories, carbs_g, protein_g, fat_g, created_at,
                              updated_at
                    """,
                    subject,
                    meal_id,
                    product_id,
                    snapshot["ingredient_name"],
                    grams,
                    snapshot["calories"],
                    snapshot["carbs_g"],
                    snapshot["protein_g"],
                    snapshot["fat_g"],
                )
                payload = self._require_row_dict(
                    row,
                    "Expected INSERT ... RETURNING for meal_items.",
                )

                if product_id is not None:
                    # The counter is a lifetime usage signal, so this internal
                    # update intentionally avoids touching the product's
                    # updated_at metadata.
                    await connection.execute(
                        """
                        UPDATE food_products
                        SET usage_count = COALESCE(usage_count, 0) + 1
                        WHERE subject = $1 AND id = $2
                        """,
                        subject,
                        product_id,
                    )

                return payload

    async def update_meal_item(
        self,
        subject: str,
        meal_item_id: int,
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
    ) -> dict[str, object] | None:
        """Replace one meal item owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_item_id: Meal-item identifier to update.
            meal_id: Replacement parent meal identifier.
            grams: Replacement consumed grams.
            ingredient_name: Replacement free-text ingredient name.
            product_id: Replacement catalog product identifier, if any.
            calories: Replacement manual calories for non-catalog items.
            carbs_g: Replacement manual carbohydrate grams.
            protein_g: Replacement manual protein grams.
            fat_g: Replacement manual fat grams.

        Returns:
            dict[str, object] | None: Updated meal item row, or `None` when
                the row does not exist for the subject.

        Raises:
            RuntimeError: If the meal or referenced product is invalid.
            ValueError: If manual nutrient values are incomplete.
            Exception: Propagated from asyncpg when the update fails.
        """

        await self._require_meal(subject, meal_id)
        snapshot = await self._build_meal_item_snapshot(
            subject=subject,
            product_id=product_id,
            ingredient_name=ingredient_name,
            grams=grams,
            calories=calories,
            carbs_g=carbs_g,
            protein_g=protein_g,
            fat_g=fat_g,
        )

        row = await self._fetchrow(
            """
            UPDATE meal_items
            SET
                meal_id = $3,
                product_id = $4,
                ingredient_name = $5,
                grams = $6,
                calories = $7,
                carbs_g = $8,
                protein_g = $9,
                fat_g = $10,
                updated_at = NOW()
            WHERE subject = $1 AND id = $2
            RETURNING id, subject, meal_id, product_id, ingredient_name, grams,
                      calories, carbs_g, protein_g, fat_g, created_at, updated_at
            """,
            subject,
            meal_item_id,
            meal_id,
            product_id,
            snapshot["ingredient_name"],
            grams,
            snapshot["calories"],
            snapshot["carbs_g"],
            snapshot["protein_g"],
            snapshot["fat_g"],
        )
        return self._row_to_dict(row)

    async def delete_meal_item(
        self,
        subject: str,
        meal_item_id: int,
    ) -> dict[str, object]:
        """Delete one meal item owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_item_id: Meal-item identifier to delete.

        Returns:
            dict[str, object]: Deletion result with the meal-item id.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        command = await self._execute(
            "DELETE FROM meal_items WHERE subject = $1 AND id = $2",
            subject,
            meal_item_id,
        )
        return {"deleted": command != "DELETE 0", "meal_item_id": meal_item_id}

    async def list_activities(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        external_source: str | None = None,
    ) -> list[dict[str, object]]:
        """List activity entries for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            external_source: Optional external-source filter such as `strava`.

        Returns:
            list[dict[str, object]]: Activity rows ordered by date and id.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        filters = ["subject = $1"]
        args: list[object] = [subject]

        if date_from is not None:
            args.append(_parse_iso_date(date_from))
            filters.append(f"activity_date >= ${len(args)}")

        if date_to is not None:
            args.append(_parse_iso_date(date_to))
            filters.append(f"activity_date <= ${len(args)}")

        if external_source is not None:
            args.append(external_source)
            filters.append(f"external_source = ${len(args)}")

        rows = await self._fetch(
            f"""
            SELECT id, subject, activity_date, title, external_source,
                   external_activity_id, athlete_id, sport_type,
                   distance_meters, moving_time_seconds, elapsed_time_seconds,
                   total_elevation_gain_meters, average_speed_mps, max_speed_mps,
                   average_heartrate, max_heartrate, average_watts,
                   weighted_average_watts, calories, kilojoules, suffer_score,
                   trainer, commute, manual, is_private, zones, laps, streams,
                   raw_payload, notes_markdown, created_at, updated_at
            FROM activity_entries
            WHERE {' AND '.join(filters)}
            ORDER BY activity_date DESC, id DESC
            """,
            *args,
        )
        return self._rows_to_dicts(rows)

    async def get_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object] | None:
        """Read one activity entry owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            activity_id: Activity identifier to fetch.

        Returns:
            dict[str, object] | None: Activity row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT id, subject, activity_date, title, external_source,
                   external_activity_id, athlete_id, sport_type,
                   distance_meters, moving_time_seconds, elapsed_time_seconds,
                   total_elevation_gain_meters, average_speed_mps, max_speed_mps,
                   average_heartrate, max_heartrate, average_watts,
                   weighted_average_watts, calories, kilojoules, suffer_score,
                   trainer, commute, manual, is_private, zones, laps, streams,
                   raw_payload, notes_markdown, created_at, updated_at
            FROM activity_entries
            WHERE subject = $1 AND id = $2
            """,
            subject,
            activity_id,
        )
        return self._row_to_dict(row)

    async def add_activity(
        self,
        subject: str,
        activity_date: str,
        title: str,
        external_source: str | None = None,
        external_activity_id: str | None = None,
        athlete_id: str | None = None,
        sport_type: str | None = None,
        distance_meters: float | None = None,
        moving_time_seconds: int | None = None,
        elapsed_time_seconds: int | None = None,
        total_elevation_gain_meters: float | None = None,
        average_speed_mps: float | None = None,
        max_speed_mps: float | None = None,
        average_heartrate: float | None = None,
        max_heartrate: float | None = None,
        average_watts: float | None = None,
        weighted_average_watts: float | None = None,
        calories: float | None = None,
        kilojoules: float | None = None,
        suffer_score: float | None = None,
        trainer: bool = False,
        commute: bool = False,
        manual: bool = True,
        is_private: bool = False,
        zones: dict[str, object] | None = None,
        laps: list[dict[str, object]] | None = None,
        streams: dict[str, object] | None = None,
        raw_payload: dict[str, object] | None = None,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create one activity entry for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            activity_date: ISO calendar date for the activity.
            title: Human-readable activity title.
            external_source: Optional sync source such as `strava`.
            external_activity_id: Optional upstream activity id.
            athlete_id: Optional upstream athlete id.
            sport_type: Optional activity type such as `Run`.
            distance_meters: Optional distance.
            moving_time_seconds: Optional moving time.
            elapsed_time_seconds: Optional elapsed time.
            total_elevation_gain_meters: Optional elevation gain.
            average_speed_mps: Optional average speed.
            max_speed_mps: Optional max speed.
            average_heartrate: Optional average heart rate.
            max_heartrate: Optional max heart rate.
            average_watts: Optional average power.
            weighted_average_watts: Optional weighted average power.
            calories: Optional calories burned.
            kilojoules: Optional work in kilojoules.
            suffer_score: Optional training-load marker.
            trainer: Whether the activity happened on a trainer.
            commute: Whether the activity was a commute.
            manual: Whether the entry was entered manually.
            is_private: Whether the activity is private upstream.
            zones: Optional zones JSON payload.
            laps: Optional laps JSON payload.
            streams: Optional streams JSON payload.
            raw_payload: Optional full upstream payload for future reuse.
            notes_markdown: Optional freeform notes.

        Returns:
            dict[str, object]: Newly created activity row.

        Raises:
            Exception: Propagated from asyncpg when the insert fails.
        """

        row = await self._fetchrow(
            """
            INSERT INTO activity_entries (
                subject, activity_date, title, external_source,
                external_activity_id, athlete_id, sport_type, distance_meters,
                moving_time_seconds, elapsed_time_seconds,
                total_elevation_gain_meters, average_speed_mps, max_speed_mps,
                average_heartrate, max_heartrate, average_watts,
                weighted_average_watts, calories, kilojoules, suffer_score,
                trainer, commute, manual, is_private, zones, laps, streams,
                raw_payload, notes_markdown
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
                $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25,
                $26, $27, $28, $29
            )
            RETURNING id, subject, activity_date, title, external_source,
                      external_activity_id, athlete_id, sport_type,
                      distance_meters, moving_time_seconds, elapsed_time_seconds,
                      total_elevation_gain_meters, average_speed_mps, max_speed_mps,
                      average_heartrate, max_heartrate, average_watts,
                      weighted_average_watts, calories, kilojoules, suffer_score,
                      trainer, commute, manual, is_private, zones, laps, streams,
                      raw_payload, notes_markdown, created_at, updated_at
            """,
            subject,
            _parse_iso_date(activity_date),
            title,
            external_source,
            external_activity_id,
            athlete_id,
            sport_type,
            distance_meters,
            moving_time_seconds,
            elapsed_time_seconds,
            total_elevation_gain_meters,
            average_speed_mps,
            max_speed_mps,
            average_heartrate,
            max_heartrate,
            average_watts,
            weighted_average_watts,
            calories,
            kilojoules,
            suffer_score,
            trainer,
            commute,
            manual,
            is_private,
            _jsonb_value(zones),
            _jsonb_value(laps),
            _jsonb_value(streams),
            _jsonb_value(raw_payload),
            notes_markdown,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for activity_entries.",
        )

    async def update_activity(
        self,
        subject: str,
        activity_id: int,
        activity_date: str,
        title: str,
        external_source: str | None = None,
        external_activity_id: str | None = None,
        athlete_id: str | None = None,
        sport_type: str | None = None,
        distance_meters: float | None = None,
        moving_time_seconds: int | None = None,
        elapsed_time_seconds: int | None = None,
        total_elevation_gain_meters: float | None = None,
        average_speed_mps: float | None = None,
        max_speed_mps: float | None = None,
        average_heartrate: float | None = None,
        max_heartrate: float | None = None,
        average_watts: float | None = None,
        weighted_average_watts: float | None = None,
        calories: float | None = None,
        kilojoules: float | None = None,
        suffer_score: float | None = None,
        trainer: bool = False,
        commute: bool = False,
        manual: bool = True,
        is_private: bool = False,
        zones: dict[str, object] | None = None,
        laps: list[dict[str, object]] | None = None,
        streams: dict[str, object] | None = None,
        raw_payload: dict[str, object] | None = None,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one activity entry owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            activity_id: Activity identifier to update.
            activity_date: Replacement ISO calendar date.
            title: Replacement activity title.
            external_source: Replacement sync source.
            external_activity_id: Replacement upstream activity id.
            athlete_id: Replacement upstream athlete id.
            sport_type: Replacement activity type.
            distance_meters: Replacement distance.
            moving_time_seconds: Replacement moving time.
            elapsed_time_seconds: Replacement elapsed time.
            total_elevation_gain_meters: Replacement elevation gain.
            average_speed_mps: Replacement average speed.
            max_speed_mps: Replacement max speed.
            average_heartrate: Replacement average heart rate.
            max_heartrate: Replacement max heart rate.
            average_watts: Replacement average power.
            weighted_average_watts: Replacement weighted average power.
            calories: Replacement calories burned.
            kilojoules: Replacement kilojoules.
            suffer_score: Replacement training-load marker.
            trainer: Replacement trainer flag.
            commute: Replacement commute flag.
            manual: Replacement manual-entry flag.
            is_private: Replacement privacy flag.
            zones: Replacement zones payload.
            laps: Replacement laps payload.
            streams: Replacement streams payload.
            raw_payload: Replacement raw payload.
            notes_markdown: Replacement freeform notes.

        Returns:
            dict[str, object] | None: Updated activity row, or `None` when
                missing.

        Raises:
            Exception: Propagated from asyncpg when the update fails.
        """

        row = await self._fetchrow(
            """
            UPDATE activity_entries
            SET
                activity_date = $3,
                title = $4,
                external_source = $5,
                external_activity_id = $6,
                athlete_id = $7,
                sport_type = $8,
                distance_meters = $9,
                moving_time_seconds = $10,
                elapsed_time_seconds = $11,
                total_elevation_gain_meters = $12,
                average_speed_mps = $13,
                max_speed_mps = $14,
                average_heartrate = $15,
                max_heartrate = $16,
                average_watts = $17,
                weighted_average_watts = $18,
                calories = $19,
                kilojoules = $20,
                suffer_score = $21,
                trainer = $22,
                commute = $23,
                manual = $24,
                is_private = $25,
                zones = $26,
                laps = $27,
                streams = $28,
                raw_payload = $29,
                notes_markdown = $30,
                updated_at = NOW()
            WHERE subject = $1 AND id = $2
            RETURNING id, subject, activity_date, title, external_source,
                      external_activity_id, athlete_id, sport_type,
                      distance_meters, moving_time_seconds, elapsed_time_seconds,
                      total_elevation_gain_meters, average_speed_mps, max_speed_mps,
                      average_heartrate, max_heartrate, average_watts,
                      weighted_average_watts, calories, kilojoules, suffer_score,
                      trainer, commute, manual, is_private, zones, laps, streams,
                      raw_payload, notes_markdown, created_at, updated_at
            """,
            subject,
            activity_id,
            _parse_iso_date(activity_date),
            title,
            external_source,
            external_activity_id,
            athlete_id,
            sport_type,
            distance_meters,
            moving_time_seconds,
            elapsed_time_seconds,
            total_elevation_gain_meters,
            average_speed_mps,
            max_speed_mps,
            average_heartrate,
            max_heartrate,
            average_watts,
            weighted_average_watts,
            calories,
            kilojoules,
            suffer_score,
            trainer,
            commute,
            manual,
            is_private,
            _jsonb_value(zones),
            _jsonb_value(laps),
            _jsonb_value(streams),
            _jsonb_value(raw_payload),
            notes_markdown,
        )
        return self._row_to_dict(row)

    async def upsert_external_activity(
        self,
        subject: str,
        activity: dict[str, object],
    ) -> dict[str, object]:
        """Insert or update one externally sourced activity row.

        Parameters:
            subject: Stable row owner for the current caller.
            activity: Activity payload with `external_source` and
                `external_activity_id` populated by a sync service.

        Returns:
            dict[str, object]: Upsert result with `action` set to `inserted`
                or `updated`, plus the saved activity row under `item`.

        Raises:
            ValueError: If required activity fields are missing.
            Exception: Propagated from asyncpg when the lookup or write fails.
        """

        activity_kwargs = _external_activity_kwargs(activity)
        existing = await self._fetchrow(
            """
            SELECT id
            FROM activity_entries
            WHERE subject = $1
              AND external_source = $2
              AND external_activity_id = $3
            """,
            subject,
            activity_kwargs["external_source"],
            activity_kwargs["external_activity_id"],
        )

        if existing is None:
            item = await self.add_activity(subject, **activity_kwargs)
            return {"action": "inserted", "item": item}

        item = await self.update_activity(
            subject,
            activity_id=int(existing["id"]),
            **activity_kwargs,
        )
        return {
            "action": "updated",
            "item": item,
        }

    async def delete_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object]:
        """Delete one activity entry owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            activity_id: Activity identifier to delete.

        Returns:
            dict[str, object]: Deletion result with the activity id.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        command = await self._execute(
            "DELETE FROM activity_entries WHERE subject = $1 AND id = $2",
            subject,
            activity_id,
        )
        return {"deleted": command != "DELETE 0", "activity_id": activity_id}

    async def list_memory_items(
        self,
        subject: str,
        category: str | None = None,
    ) -> list[dict[str, object]]:
        """List long-term memory items for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            category: Optional category filter.

        Returns:
            list[dict[str, object]]: Memory item rows ordered by recency.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        if category is None:
            rows = await self._fetch(
                """
                SELECT id, subject, title, category, content_markdown,
                       created_at, updated_at
                FROM memory_items
                WHERE subject = $1
                ORDER BY created_at DESC, id DESC
                """,
                subject,
            )
            return self._rows_to_dicts(rows)

        rows = await self._fetch(
            """
            SELECT id, subject, title, category, content_markdown,
                   created_at, updated_at
            FROM memory_items
            WHERE subject = $1 AND category = $2
            ORDER BY created_at DESC, id DESC
            """,
            subject,
            category,
        )
        return self._rows_to_dicts(rows)

    async def get_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object] | None:
        """Read one long-term memory item owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            memory_item_id: Memory-item identifier to fetch.

        Returns:
            dict[str, object] | None: Memory row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetchrow(
            """
            SELECT id, subject, title, category, content_markdown,
                   created_at, updated_at
            FROM memory_items
            WHERE subject = $1 AND id = $2
            """,
            subject,
            memory_item_id,
        )
        return self._row_to_dict(row)

    async def add_memory_item(
        self,
        subject: str,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object]:
        """Create one long-term memory item for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            title: Short title for the memory entry.
            content_markdown: Main markdown content to remember.
            category: Optional category or tag.

        Returns:
            dict[str, object]: Newly created memory row.

        Raises:
            Exception: Propagated from asyncpg when the insert fails.
        """

        row = await self._fetchrow(
            """
            INSERT INTO memory_items (subject, title, category, content_markdown)
            VALUES ($1, $2, $3, $4)
            RETURNING id, subject, title, category, content_markdown,
                      created_at, updated_at
            """,
            subject,
            title,
            category,
            content_markdown,
        )
        return self._require_row_dict(
            row,
            "Expected INSERT ... RETURNING for memory_items.",
        )

    async def update_memory_item(
        self,
        subject: str,
        memory_item_id: int,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object] | None:
        """Replace one long-term memory item owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            memory_item_id: Memory-item identifier to update.
            title: Replacement title.
            content_markdown: Replacement markdown content.
            category: Replacement category or tag.

        Returns:
            dict[str, object] | None: Updated memory row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the update fails.
        """

        row = await self._fetchrow(
            """
            UPDATE memory_items
            SET
                title = $3,
                category = $4,
                content_markdown = $5,
                updated_at = NOW()
            WHERE subject = $1 AND id = $2
            RETURNING id, subject, title, category, content_markdown,
                      created_at, updated_at
            """,
            subject,
            memory_item_id,
            title,
            category,
            content_markdown,
        )
        return self._row_to_dict(row)

    async def delete_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object]:
        """Delete one long-term memory item owned by a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            memory_item_id: Memory-item identifier to delete.

        Returns:
            dict[str, object]: Deletion result with the memory-item id.

        Raises:
            Exception: Propagated from asyncpg when the delete fails.
        """

        command = await self._execute(
            "DELETE FROM memory_items WHERE subject = $1 AND id = $2",
            subject,
            memory_item_id,
        )
        return {"deleted": command != "DELETE 0", "memory_item_id": memory_item_id}

    async def get_daily_summary(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Compute the daily target-vs-actual summary for one date.

        Parameters:
            subject: Stable row owner for the current caller.
            target_date: ISO calendar date to summarize.

        Returns:
            dict[str, object]: Combined target, actual, and count fields.

        Raises:
            Exception: Propagated from asyncpg when the summary queries fail.
        """

        parsed_date = _parse_iso_date(target_date)

        target_row = await self._fetchrow(
            """
            SELECT target_food_calories, target_exercise_calories,
                   target_protein_g, target_carbs_g, target_fat_g
            FROM daily_targets
            WHERE subject = $1 AND target_date = $2
            """,
            subject,
            parsed_date,
        )
        meal_row = await self._fetchrow(
            """
            SELECT
                COALESCE(SUM(mi.calories), 0) AS actual_food_calories,
                COALESCE(SUM(mi.protein_g), 0) AS actual_protein_g,
                COALESCE(SUM(mi.carbs_g), 0) AS actual_carbs_g,
                COALESCE(SUM(mi.fat_g), 0) AS actual_fat_g,
                COUNT(DISTINCT dm.id)::INTEGER AS meals_count,
                COUNT(mi.id)::INTEGER AS meal_items_count
            FROM daily_meals dm
            LEFT JOIN meal_items mi
                ON mi.subject = dm.subject AND mi.meal_id = dm.id
            WHERE dm.subject = $1 AND dm.meal_date = $2
            """,
            subject,
            parsed_date,
        )
        activity_row = await self._fetchrow(
            """
            SELECT
                COALESCE(SUM(COALESCE(calories, 0)), 0) AS actual_exercise_calories,
                COUNT(id)::INTEGER AS activities_count
            FROM activity_entries
            WHERE subject = $1 AND activity_date = $2
            """,
            subject,
            parsed_date,
        )

        actual_food_calories = _as_float(meal_row["actual_food_calories"]) or 0.0
        actual_exercise_calories = (
            _as_float(activity_row["actual_exercise_calories"]) or 0.0
        )

        return {
            "target_date": parsed_date.isoformat(),
            "target_food_calories": _nullable_record_value(
                target_row,
                "target_food_calories",
            ),
            "target_exercise_calories": _nullable_record_value(
                target_row,
                "target_exercise_calories",
            ),
            "target_protein_g": _nullable_record_value(target_row, "target_protein_g"),
            "target_carbs_g": _nullable_record_value(target_row, "target_carbs_g"),
            "target_fat_g": _nullable_record_value(target_row, "target_fat_g"),
            "actual_food_calories": actual_food_calories,
            "actual_exercise_calories": actual_exercise_calories,
            "actual_protein_g": _as_float(meal_row["actual_protein_g"]) or 0.0,
            "actual_carbs_g": _as_float(meal_row["actual_carbs_g"]) or 0.0,
            "actual_fat_g": _as_float(meal_row["actual_fat_g"]) or 0.0,
            # Net calories remain easy to explain to the agent: food in minus
            # exercise out for the selected business date.
            "net_calories": round(actual_food_calories - actual_exercise_calories, 2),
            "meals_count": _as_int(meal_row["meals_count"]) or 0,
            "meal_items_count": _as_int(meal_row["meal_items_count"]) or 0,
            "activities_count": _as_int(activity_row["activities_count"]) or 0,
        }

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
            *args: Positional SQL parameters.

        Returns:
            str: asyncpg command tag returned by the write statement.

        Raises:
            Exception: Propagated from asyncpg when the write fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def _fetchrow(
        self,
        query: str,
        *args: object,
    ) -> asyncpg.Record | None:
        """Run a read query and return the first matching row.

        Parameters:
            query: SQL statement to execute.
            *args: Positional SQL parameters.

        Returns:
            asyncpg.Record | None: First matching row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            return await connection.fetchrow(query, *args)

    async def _fetch(self, query: str, *args: object) -> list[asyncpg.Record]:
        """Run a read query and return all matching rows.

        Parameters:
            query: SQL statement to execute.
            *args: Positional SQL parameters.

        Returns:
            list[asyncpg.Record]: All matching rows from the database.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        pool = await self._ensure_pool()
        async with pool.acquire() as connection:
            return list(await connection.fetch(query, *args))

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
                    # Supabase recommends a pooler connection for serverless
                    # platforms such as Vercel. Disabling asyncpg's statement
                    # cache keeps the app compatible with transaction poolers.
                    statement_cache_size=0,
                )

                # Remote environments do not run the Docker init script, so the
                # application keeps an additive schema bootstrap here as well.
                async with self._pool.acquire() as connection:
                    await connection.execute(self.schema_sql)

        return self._pool

    async def _get_markdown_document(self, subject: str, column: str) -> str:
        """Read one markdown document column from the singleton user row.

        Parameters:
            subject: Stable row owner for the current caller.
            column: Whitelisted markdown column name to fetch.

        Returns:
            str: Stored markdown, or an empty string when missing.

        Raises:
            ValueError: If the requested document column is not whitelisted.
            Exception: Propagated from asyncpg when the query fails.
        """

        if column not in _DOCUMENT_COLUMNS:
            raise ValueError(f"Unsupported markdown document column: {column}")

        row = await self._fetchrow(
            f"SELECT {column} FROM user_profiles WHERE subject = $1",
            subject,
        )
        if row is None:
            return ""
        return str(row[column] or "")

    async def _upsert_user_profile_fields(
        self,
        subject: str,
        login: str | None,
        fields: dict[str, object],
    ) -> None:
        """Upsert selected columns on the singleton `user_profiles` row.

        Parameters:
            subject: Stable row owner for the current caller.
            login: Optional friendly login captured from the auth layer.
            fields: Column-value mapping to store on the singleton row.

        Returns:
            None.

        Raises:
            ValueError: If an unexpected column is supplied.
            Exception: Propagated from asyncpg when the upsert fails.
        """

        allowed_columns = {
            "profile_markdown",
            "diet_preferences_markdown",
            "diet_goals_markdown",
            "training_goals_markdown",
            "weight_kg",
            "height_cm",
            "ftp_watts",
        }
        invalid_columns = set(fields) - allowed_columns
        if invalid_columns:
            raise ValueError(
                "Unsupported user_profiles columns: "
                + ", ".join(sorted(invalid_columns))
            )

        insert_columns = ["subject", "login", *fields.keys()]
        insert_values = [subject, login, *fields.values()]
        placeholders = ", ".join(
            f"${index}" for index in range(1, len(insert_values) + 1)
        )
        updates = [
            "login = COALESCE(EXCLUDED.login, user_profiles.login)",
            *[f"{column} = EXCLUDED.{column}" for column in fields],
            "updated_at = NOW()",
        ]

        await self._execute(
            f"""
            INSERT INTO user_profiles ({", ".join(insert_columns)})
            VALUES ({placeholders})
            ON CONFLICT (subject) DO UPDATE
            SET {", ".join(updates)}
            """,
            *insert_values,
        )

    async def _fetch_product_record(
        self,
        subject: str,
        product_id: int,
        connection: asyncpg.Connection | None = None,
    ) -> asyncpg.Record:
        """Load one product record and fail clearly when it is missing.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Product identifier expected to belong to the subject.
            connection: Optional active connection used to keep the lookup
                inside a caller-managed transaction.

        Returns:
            asyncpg.Record: Product row used for nutrition snapshotting.

        Raises:
            RuntimeError: If the product does not belong to the subject.
            Exception: Propagated from asyncpg when the query fails.
        """

        query = """
            SELECT id, name, calories_per_100g, carbs_g_per_100g,
                   protein_g_per_100g, fat_g_per_100g
            FROM food_products
            WHERE subject = $1 AND id = $2
            """
        if connection is None:
            row = await self._fetchrow(query, subject, product_id)
        else:
            row = await connection.fetchrow(query, subject, product_id)

        if row is None:
            raise RuntimeError(
                f"Food product {product_id} was not found for the current user."
            )
        return row

    async def _fetch_meal(
        self,
        subject: str,
        meal_id: int,
        connection: asyncpg.Connection | None = None,
    ) -> asyncpg.Record | None:
        """Load one meal header row for the current subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier to fetch.
            connection: Optional active connection used to keep the lookup
                inside a caller-managed transaction.

        Returns:
            asyncpg.Record | None: Meal row, or `None` when missing.

        Raises:
            Exception: Propagated from asyncpg when the query fails.
        """

        query = """
            SELECT id, subject, meal_date, meal_label, notes_markdown,
                   created_at, updated_at
            FROM daily_meals
            WHERE subject = $1 AND id = $2
            """
        if connection is None:
            return await self._fetchrow(query, subject, meal_id)
        return await connection.fetchrow(query, subject, meal_id)

    async def _require_meal(
        self,
        subject: str,
        meal_id: int,
        connection: asyncpg.Connection | None = None,
    ) -> asyncpg.Record:
        """Load one meal header and fail clearly when it is missing.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier expected to belong to the subject.
            connection: Optional active connection used to keep the lookup
                inside a caller-managed transaction.

        Returns:
            asyncpg.Record: Meal row owned by the current subject.

        Raises:
            RuntimeError: If the meal does not belong to the subject.
            Exception: Propagated from asyncpg when the query fails.
        """

        row = await self._fetch_meal(subject, meal_id, connection=connection)
        if row is None:
            raise RuntimeError(f"Meal {meal_id} was not found for the current user.")
        return row

    async def _build_meal_item_snapshot(
        self,
        subject: str,
        product_id: int | None,
        ingredient_name: str | None,
        grams: float,
        calories: float | None,
        carbs_g: float | None,
        protein_g: float | None,
        fat_g: float | None,
        connection: asyncpg.Connection | None = None,
    ) -> dict[str, object]:
        """Build the stored nutrition snapshot for a meal item.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Optional catalog product used for auto-calculation.
            ingredient_name: Free-text ingredient name for manual items or
                optional label override for catalog items.
            grams: Consumed grams used for nutrient scaling.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.
            connection: Optional active connection used to keep product lookup
                inside a caller-managed transaction.

        Returns:
            dict[str, object]: Snapshot fields ready for insertion or update.

        Raises:
            RuntimeError: If the referenced product is invalid.
            ValueError: If the provided values do not satisfy the snapshot rules.
            Exception: Propagated from asyncpg when product lookups fail.
        """

        if grams <= 0:
            raise ValueError("grams must be greater than 0.")

        if product_id is not None:
            product_row = await self._fetch_product_record(
                subject,
                product_id,
                connection=connection,
            )
            resolved_name = ingredient_name.strip() if ingredient_name else ""
            if not resolved_name:
                resolved_name = str(product_row["name"])

            # Historical meal items must keep the nutrient snapshot that was
            # true when they were logged, even if the product is edited later.
            return {
                "ingredient_name": resolved_name,
                "calories": _scaled_metric(product_row["calories_per_100g"], grams),
                "carbs_g": _scaled_metric(product_row["carbs_g_per_100g"], grams),
                "protein_g": _scaled_metric(product_row["protein_g_per_100g"], grams),
                "fat_g": _scaled_metric(product_row["fat_g_per_100g"], grams),
            }

        if ingredient_name is None or not ingredient_name.strip():
            raise ValueError(
                "ingredient_name is required when product_id is not provided."
            )
        if None in {calories, carbs_g, protein_g, fat_g}:
            raise ValueError(
                "calories, carbs_g, protein_g, and fat_g are required "
                "for manual meal items."
            )

        return {
            "ingredient_name": ingredient_name.strip(),
            "calories": round(float(calories), 2),
            "carbs_g": round(float(carbs_g), 2),
            "protein_g": round(float(protein_g), 2),
            "fat_g": round(float(fat_g), 2),
        }

    def _row_to_dict(self, row: asyncpg.Record | None) -> dict[str, object] | None:
        """Convert one asyncpg row into a JSON-safe dictionary.

        Parameters:
            row: Asyncpg row returned by the database.

        Returns:
            dict[str, object] | None: Serialized row, or `None` when missing.

        Raises:
            This helper does not raise errors directly.
        """

        if row is None:
            return None

        # Postgres returns JSONB columns as strings with the current asyncpg
        # parameter strategy, so we normalize those fields back into native
        # dict/list values before exposing them through MCP tools.
        return {
            key: _serialize_value(key, value) for key, value in dict(row).items()
        }

    def _rows_to_dicts(self, rows: list[asyncpg.Record]) -> list[dict[str, object]]:
        """Convert multiple asyncpg rows into JSON-safe dictionaries.

        Parameters:
            rows: Asyncpg rows returned by the database.

        Returns:
            list[dict[str, object]]: Serialized rows ready for MCP responses.

        Raises:
            This helper does not raise errors directly.
        """

        return [self._require_row_dict(row, "Unexpected missing row.") for row in rows]

    def _require_row_dict(
        self,
        row: asyncpg.Record | None,
        message: str,
    ) -> dict[str, object]:
        """Convert a row to a dict and fail clearly when it is unexpectedly missing.

        Parameters:
            row: Asyncpg row expected to be present.
            message: Error message raised when the row is missing.

        Returns:
            dict[str, object]: JSON-safe serialized row.

        Raises:
            RuntimeError: If the row is unexpectedly missing.
        """

        payload = self._row_to_dict(row)
        if payload is None:
            raise RuntimeError(message)
        return payload


def build_user_store(settings: Settings) -> UserStore:
    """Create the configured Postgres-backed user store.

    Parameters:
        settings: Normalized runtime settings.

    Returns:
        UserStore: The Postgres storage backend used by the pilot.

    Raises:
        RuntimeError: If the database URL is unexpectedly missing.
    """

    if settings.database_url is None:
        raise RuntimeError("DATABASE_URL must be validated before building the store.")

    return PostgresUserStore(database_url=settings.database_url)


def _parse_iso_date(value: str) -> date:
    """Parse an ISO date string used by the MCP tool surface.

    Parameters:
        value: ISO date string such as `2026-04-14`.

    Returns:
        date: Parsed calendar date.

    Raises:
        ValueError: If the input is not a valid ISO date string.
    """

    return date.fromisoformat(value)


def _external_activity_kwargs(activity: dict[str, object]) -> dict[str, Any]:
    """Normalize an external-sync activity payload for storage methods.

    Parameters:
        activity: Raw activity payload prepared by an external service mapper.

    Returns:
        dict[str, Any]: Keyword arguments accepted by `add_activity` and
            `update_activity`.

    Raises:
        ValueError: If required activity fields are missing.
    """

    return {
        "activity_date": _required_activity_text(activity, "activity_date"),
        "title": _required_activity_text(activity, "title"),
        "external_source": _required_activity_text(activity, "external_source"),
        "external_activity_id": _required_activity_text(
            activity,
            "external_activity_id",
        ),
        "athlete_id": _optional_activity_text(activity, "athlete_id"),
        "sport_type": _optional_activity_text(activity, "sport_type"),
        "distance_meters": _optional_activity_float(activity, "distance_meters"),
        "moving_time_seconds": _optional_activity_int(
            activity,
            "moving_time_seconds",
        ),
        "elapsed_time_seconds": _optional_activity_int(
            activity,
            "elapsed_time_seconds",
        ),
        "total_elevation_gain_meters": _optional_activity_float(
            activity,
            "total_elevation_gain_meters",
        ),
        "average_speed_mps": _optional_activity_float(activity, "average_speed_mps"),
        "max_speed_mps": _optional_activity_float(activity, "max_speed_mps"),
        "average_heartrate": _optional_activity_float(activity, "average_heartrate"),
        "max_heartrate": _optional_activity_float(activity, "max_heartrate"),
        "average_watts": _optional_activity_float(activity, "average_watts"),
        "weighted_average_watts": _optional_activity_float(
            activity,
            "weighted_average_watts",
        ),
        "calories": _optional_activity_float(activity, "calories"),
        "kilojoules": _optional_activity_float(activity, "kilojoules"),
        "suffer_score": _optional_activity_float(activity, "suffer_score"),
        "trainer": bool(activity.get("trainer", False)),
        "commute": bool(activity.get("commute", False)),
        "manual": bool(activity.get("manual", False)),
        "is_private": bool(activity.get("is_private", False)),
        "zones": (
            activity.get("zones") if isinstance(activity.get("zones"), dict) else None
        ),
        "laps": (
            activity.get("laps") if isinstance(activity.get("laps"), list) else None
        ),
        "streams": (
            activity.get("streams")
            if isinstance(activity.get("streams"), dict)
            else None
        ),
        "raw_payload": (
            activity.get("raw_payload")
            if isinstance(activity.get("raw_payload"), dict)
            else None
        ),
        "notes_markdown": str(activity.get("notes_markdown") or ""),
    }


def _required_activity_text(activity: dict[str, object], key: str) -> str:
    """Read a required non-empty string from an activity payload.

    Parameters:
        activity: Activity payload to read.
        key: Required key name.

    Returns:
        str: Trimmed text value.

    Raises:
        ValueError: If the key is missing or empty.
    """

    value = activity.get(key)
    if value is None:
        raise ValueError(f"{key} is required for external activity upsert.")
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{key} is required for external activity upsert.")
    return cleaned


def _optional_activity_text(activity: dict[str, object], key: str) -> str | None:
    """Read an optional string from an activity payload.

    Parameters:
        activity: Activity payload to read.
        key: Optional key name.

    Returns:
        str | None: Trimmed text value or `None`.

    Raises:
        This helper does not raise errors directly.
    """

    value = activity.get(key)
    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _optional_activity_float(activity: dict[str, object], key: str) -> float | None:
    """Read an optional float from an activity payload.

    Parameters:
        activity: Activity payload to read.
        key: Optional key name.

    Returns:
        float | None: Float value or `None`.

    Raises:
        ValueError: If a present value cannot be converted to `float`.
    """

    value = activity.get(key)
    if value is None:
        return None
    return float(value)


def _optional_activity_int(activity: dict[str, object], key: str) -> int | None:
    """Read an optional integer from an activity payload.

    Parameters:
        activity: Activity payload to read.
        key: Optional key name.

    Returns:
        int | None: Integer value or `None`.

    Raises:
        ValueError: If a present value cannot be converted to `int`.
    """

    value = activity.get(key)
    if value is None:
        return None
    return int(value)


def _normalize_daily_metric_type(metric_type: str) -> str:
    """Normalize and validate a supported daily metric type.

    Parameters:
        metric_type: Caller-provided metric type string.

    Returns:
        str: Normalized metric type used in storage and responses.

    Raises:
        ValueError: If the metric type is empty or unsupported.
    """

    normalized_type = metric_type.strip().lower()
    if normalized_type not in DAILY_METRIC_TYPES:
        supported = ", ".join(sorted(DAILY_METRIC_TYPES))
        raise ValueError(
            f"Unsupported metric_type '{metric_type}'. "
            f"Supported metric types: {supported}."
        )
    return normalized_type


def _validate_daily_metric_value(metric_type: str, value: object) -> float:
    """Validate one daily metric value using type-specific pilot rules.

    Parameters:
        metric_type: Normalized supported metric type.
        value: Caller-provided numeric value.

    Returns:
        float: Normalized value to store in Postgres.

    Raises:
        ValueError: If the value is non-numeric, non-finite, or out of range.
    """

    if isinstance(value, bool):
        raise ValueError("value must be a finite number.")

    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be a finite number.") from exc

    if not isfinite(numeric_value):
        raise ValueError("value must be a finite number.")

    if metric_type == "weight" and numeric_value <= 0:
        raise ValueError("weight value must be greater than 0.")

    if metric_type == "steps":
        if numeric_value < 0 or not numeric_value.is_integer():
            raise ValueError(
                "steps value must be a whole number greater than or equal to 0."
            )

    if metric_type == "sleep_hours" and not 0 <= numeric_value <= 24:
        raise ValueError("sleep_hours value must be between 0 and 24.")

    return numeric_value


def _scaled_metric(per_100g: object, grams: float) -> float:
    """Scale a per-100g nutrient value into a consumed-grams snapshot.

    Parameters:
        per_100g: Raw per-100g nutrient value from the product catalog.
        grams: Consumed grams for the meal item.

    Returns:
        float: Rounded nutrient snapshot used for the meal item row.

    Raises:
        ValueError: If the value cannot be converted to a float.
    """

    return round(float(per_100g) * grams / 100.0, 2)


def _serialize_value(key: str, value: object) -> object:
    """Convert database-native values into JSON-safe response values.

    Parameters:
        key: Column name associated with the raw value.
        value: Raw value returned by asyncpg.

    Returns:
        object: Serialized value ready for MCP responses.

    Raises:
        This helper does not raise errors directly.
    """

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if key in _JSON_COLUMNS and isinstance(value, str):
        return json.loads(value)
    return value


def _jsonb_value(value: object | None) -> object | None:
    """Wrap Python JSON-like values so asyncpg stores them as JSONB.

    Parameters:
        value: Optional Python dict, list, or scalar intended for a JSONB column.

    Returns:
        object | None: JSON string accepted by Postgres JSONB columns, or
            `None` for null columns.

    Raises:
        This helper does not raise errors directly.
    """

    if value is None:
        return None
    return json.dumps(value)


def _nullable_record_value(
    row: asyncpg.Record | None,
    key: str,
) -> float | None:
    """Read one nullable float-like value from an optional record.

    Parameters:
        row: Optional record returned by asyncpg.
        key: Column name to read.

    Returns:
        float | None: Converted float when present, otherwise `None`.

    Raises:
        ValueError: If the raw value cannot be converted to `float`.
    """

    if row is None or row[key] is None:
        return None
    return float(row[key])


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
