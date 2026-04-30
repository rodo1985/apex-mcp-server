"""In-process and HTTP tests for the wellness MCP server."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from math import isfinite
from typing import Any

import httpx
import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from apex_mcp_server.config import Settings
from apex_mcp_server.models import ProfileSaveResult, UserData, UserDataSaveResult
from apex_mcp_server.server import create_mcp_server
from apex_mcp_server.storage import UserStore


class InMemoryUserStore(UserStore):
    """In-memory test double that mirrors the Postgres wellness store.

    Parameters:
        None.

    Returns:
        InMemoryUserStore: Storage double used for fast MCP surface tests.
    """

    def __init__(self) -> None:
        """Initialize the in-memory dictionaries used by the fake store.

        Parameters:
            None.

        Returns:
            None.
        """

        self.user_rows: dict[str, dict[str, object]] = {}
        self.products: dict[str, dict[int, dict[str, object]]] = {}
        self.daily_targets: dict[str, dict[str, dict[str, object]]] = {}
        self.daily_metrics: dict[str, dict[str, dict[str, object]]] = {}
        self.meals: dict[str, dict[int, dict[str, object]]] = {}
        self.meal_items: dict[str, dict[int, dict[str, object]]] = {}
        self.activities: dict[str, dict[int, dict[str, object]]] = {}
        self.external_tokens: dict[str, dict[str, dict[str, object]]] = {}
        self.memory_items: dict[str, dict[int, dict[str, object]]] = {}
        self._counters = {
            "product": 0,
            "target": 0,
            "metric": 0,
            "meal": 0,
            "meal_item": 0,
            "activity": 0,
            "memory": 0,
        }

    def _timestamp(self) -> str:
        """Return a stable ISO timestamp for fake row bookkeeping.

        Parameters:
            None.

        Returns:
            str: UTC timestamp string.
        """

        return datetime.now(tz=UTC).isoformat()

    def _copy(self, payload: object) -> object:
        """Return a deep copy so tests do not mutate stored state by accident.

        Parameters:
            payload: Stored row or collection payload.

        Returns:
            object: Deep-copied payload.
        """

        return deepcopy(payload)

    def _next_id(self, kind: str) -> int:
        """Return the next integer identifier for one collection type.

        Parameters:
            kind: Counter namespace such as `product` or `meal`.

        Returns:
            int: Incremented integer identifier.
        """

        self._counters[kind] += 1
        return self._counters[kind]

    def _user_row(self, subject: str) -> dict[str, object]:
        """Return the singleton user row for a subject, creating defaults.

        Parameters:
            subject: Stable row owner for the current caller.

        Returns:
            dict[str, object]: Mutable singleton row for the subject.
        """

        if subject not in self.user_rows:
            now = self._timestamp()
            self.user_rows[subject] = {
                "subject": subject,
                "login": None,
                "profile_markdown": "",
                "diet_preferences_markdown": "",
                "diet_goals_markdown": "",
                "training_goals_markdown": "",
                "weight_kg": None,
                "height_cm": None,
                "ftp_watts": None,
                "created_at": now,
                "updated_at": now,
            }
        return self.user_rows[subject]

    def _set_document(
        self,
        subject: str,
        column: str,
        value: str,
        login: str | None,
    ) -> ProfileSaveResult:
        """Store one singleton markdown document for a subject.

        Parameters:
            subject: Stable row owner for the current caller.
            column: Document column name stored on the singleton row.
            value: New markdown content.
            login: Optional friendly login captured from the auth layer.

        Returns:
            ProfileSaveResult: Save confirmation matching production behavior.
        """

        row = self._user_row(subject)
        row[column] = value
        if login is not None:
            row["login"] = login
        row["updated_at"] = self._timestamp()
        return ProfileSaveResult(
            saved=True,
            subject=subject,
            bytes=len(value.encode("utf-8")),
        )

    def _subject_bucket(
        self,
        bucket: dict[str, dict[int, dict[str, object]]],
        subject: str,
    ) -> dict[int, dict[str, object]]:
        """Return one subject-scoped collection bucket.

        Parameters:
            bucket: Top-level collection storage.
            subject: Stable row owner for the current caller.

        Returns:
            dict[int, dict[str, object]]: Mutable subject-scoped bucket.
        """

        return bucket.setdefault(subject, {})

    def _subject_date_bucket(
        self,
        bucket: dict[str, dict[str, dict[str, object]]],
        subject: str,
    ) -> dict[str, dict[str, object]]:
        """Return one subject-scoped date-keyed collection bucket.

        Parameters:
            bucket: Top-level date-keyed collection storage.
            subject: Stable row owner for the current caller.

        Returns:
            dict[str, dict[str, object]]: Mutable subject-scoped bucket.
        """

        return bucket.setdefault(subject, {})

    def _get_product_row(self, subject: str, product_id: int) -> dict[str, object]:
        """Return a product row or fail when it is missing for the subject.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Product identifier to fetch.

        Returns:
            dict[str, object]: Mutable product row.

        Raises:
            RuntimeError: If the product does not exist for the subject.
        """

        row = self._subject_bucket(self.products, subject).get(product_id)
        if row is None:
            raise RuntimeError(
                f"Food product {product_id} was not found for the current user."
            )
        return row

    def _get_meal_row(self, subject: str, meal_id: int) -> dict[str, object]:
        """Return a meal row or fail when it is missing for the subject.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Meal identifier to fetch.

        Returns:
            dict[str, object]: Mutable meal row.

        Raises:
            RuntimeError: If the meal does not exist for the subject.
        """

        row = self._subject_bucket(self.meals, subject).get(meal_id)
        if row is None:
            raise RuntimeError(f"Meal {meal_id} was not found for the current user.")
        return row

    def _scaled_metric(self, per_100g: object, grams: float) -> float:
        """Scale a per-100g nutrient value for one meal-item snapshot.

        Parameters:
            per_100g: Product nutrient value stored per 100 grams.
            grams: Consumed grams for the meal item.

        Returns:
            float: Rounded nutrient snapshot.
        """

        return round(float(per_100g) * grams / 100.0, 2)

    def _build_meal_item_snapshot(
        self,
        subject: str,
        product_id: int | None,
        ingredient_name: str | None,
        grams: float,
        calories: float | None,
        carbs_g: float | None,
        protein_g: float | None,
        fat_g: float | None,
    ) -> dict[str, object]:
        """Build the stored meal-item nutrient snapshot.

        Parameters:
            subject: Stable row owner for the current caller.
            product_id: Optional product identifier used for auto-scaling.
            ingredient_name: Free-text name or optional product label override.
            grams: Consumed grams for the item.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.

        Returns:
            dict[str, object]: Snapshot fields stored on the meal item.

        Raises:
            RuntimeError: If a referenced product is missing.
            ValueError: If the provided data is incomplete.
        """

        if grams <= 0:
            raise ValueError("grams must be greater than 0.")

        if product_id is not None:
            product = self._get_product_row(subject, product_id)
            resolved_name = ingredient_name.strip() if ingredient_name else ""
            if not resolved_name:
                resolved_name = str(product["name"])

            return {
                "ingredient_name": resolved_name,
                "calories": self._scaled_metric(product["calories_per_100g"], grams),
                "carbs_g": self._scaled_metric(product["carbs_g_per_100g"], grams),
                "protein_g": self._scaled_metric(
                    product["protein_g_per_100g"], grams
                ),
                "fat_g": self._scaled_metric(product["fat_g_per_100g"], grams),
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

    def _normalize_metric_type(self, metric_type: str) -> str:
        """Normalize and validate one daily metric type.

        Parameters:
            metric_type: Caller-provided metric type string.

        Returns:
            str: Normalized metric type used by fake storage.

        Raises:
            ValueError: If the metric type is unsupported.
        """

        normalized_type = metric_type.strip().lower()
        if normalized_type not in {"weight", "steps", "sleep_hours"}:
            raise ValueError(
                f"Unsupported metric_type '{metric_type}'. "
                "Supported metric types: sleep_hours, steps, weight."
            )
        return normalized_type

    def _validate_metric_value(self, metric_type: str, value: object) -> float:
        """Validate a fake daily metric value with production-like rules.

        Parameters:
            metric_type: Normalized supported metric type.
            value: Caller-provided numeric value.

        Returns:
            float: Normalized metric value.

        Raises:
            ValueError: If the value is non-finite or out of range.
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

    async def get_profile(self, subject: str) -> str:
        """Return the stored profile markdown for a subject."""

        return str(self._user_row(subject)["profile_markdown"])

    async def set_profile(
        self,
        subject: str,
        profile_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Store profile markdown in memory and return a save summary."""

        return self._set_document(subject, "profile_markdown", profile_markdown, login)

    async def get_user_data(self, subject: str) -> UserData:
        """Return numeric user data or an all-null structure when missing."""

        row = self._user_row(subject)
        return UserData(
            weight_kg=row["weight_kg"],
            height_cm=row["height_cm"],
            ftp_watts=row["ftp_watts"],
        )

    async def set_user_data(
        self,
        subject: str,
        data: UserData,
        login: str | None = None,
    ) -> UserDataSaveResult:
        """Store numeric user data in memory and return a save summary."""

        row = self._user_row(subject)
        row["weight_kg"] = data.weight_kg
        row["height_cm"] = data.height_cm
        row["ftp_watts"] = data.ftp_watts
        if login is not None:
            row["login"] = login
        row["updated_at"] = self._timestamp()
        return UserDataSaveResult(
            saved=True,
            subject=subject,
            weight_kg=data.weight_kg,
            height_cm=data.height_cm,
            ftp_watts=data.ftp_watts,
        )

    async def get_diet_preferences(self, subject: str) -> str:
        """Return the stored diet-preferences markdown for a subject."""

        return str(self._user_row(subject)["diet_preferences_markdown"])

    async def set_diet_preferences(
        self,
        subject: str,
        diet_preferences_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Store diet-preferences markdown in memory."""

        return self._set_document(
            subject,
            "diet_preferences_markdown",
            diet_preferences_markdown,
            login,
        )

    async def get_diet_goals(self, subject: str) -> str:
        """Return the stored diet-goals markdown for a subject."""

        return str(self._user_row(subject)["diet_goals_markdown"])

    async def set_diet_goals(
        self,
        subject: str,
        diet_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Store diet-goals markdown in memory."""

        return self._set_document(
            subject,
            "diet_goals_markdown",
            diet_goals_markdown,
            login,
        )

    async def get_training_goals(self, subject: str) -> str:
        """Return the stored training-goals markdown for a subject."""

        return str(self._user_row(subject)["training_goals_markdown"])

    async def set_training_goals(
        self,
        subject: str,
        training_goals_markdown: str,
        login: str | None = None,
    ) -> ProfileSaveResult:
        """Store training-goals markdown in memory."""

        return self._set_document(
            subject,
            "training_goals_markdown",
            training_goals_markdown,
            login,
        )

    async def list_products(self, subject: str) -> list[dict[str, object]]:
        """List products owned by one subject."""

        rows = sorted(
            self._subject_bucket(self.products, subject).values(),
            key=lambda row: (str(row["name"]).lower(), int(row["id"])),
        )
        return self._copy(rows)

    async def get_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object] | None:
        """Return one product row for a subject."""

        row = self._subject_bucket(self.products, subject).get(product_id)
        return self._copy(row) if row is not None else None

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
        """Create one food product for a subject with zero usage.

        Parameters:
            subject: Stable row owner for the current caller.
            name: Product display name.
            default_serving_g: Optional common serving size in grams.
            calories_per_100g: Calories per 100 grams.
            carbs_g_per_100g: Carbohydrates per 100 grams.
            protein_g_per_100g: Protein per 100 grams.
            fat_g_per_100g: Fat per 100 grams.
            notes_markdown: Optional freeform product notes.

        Returns:
            dict[str, object]: Created in-memory product row.
        """

        now = self._timestamp()
        product_id = self._next_id("product")
        row = {
            "id": product_id,
            "subject": subject,
            "name": name,
            "default_serving_g": default_serving_g,
            "calories_per_100g": calories_per_100g,
            "carbs_g_per_100g": carbs_g_per_100g,
            "protein_g_per_100g": protein_g_per_100g,
            "fat_g_per_100g": fat_g_per_100g,
            "usage_count": 0,
            "notes_markdown": notes_markdown,
            "created_at": now,
            "updated_at": now,
        }
        self._subject_bucket(self.products, subject)[product_id] = row
        return self._copy(row)

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

        row = self._subject_bucket(self.products, subject).get(product_id)
        if row is None:
            return None

        row.update(
            {
                "name": name,
                "default_serving_g": default_serving_g,
                "calories_per_100g": calories_per_100g,
                "carbs_g_per_100g": carbs_g_per_100g,
                "protein_g_per_100g": protein_g_per_100g,
                "fat_g_per_100g": fat_g_per_100g,
                "notes_markdown": notes_markdown,
                "updated_at": self._timestamp(),
            }
        )
        return self._copy(row)

    async def delete_product(
        self,
        subject: str,
        product_id: int,
    ) -> dict[str, object]:
        """Delete one food product owned by a subject."""

        deleted = self._subject_bucket(self.products, subject).pop(product_id, None)
        return {"deleted": deleted is not None, "product_id": product_id}

    async def list_daily_targets(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily targets owned by one subject."""

        rows = []
        for target in self._subject_date_bucket(self.daily_targets, subject).values():
            target_date = str(target["target_date"])
            if date_from is not None and target_date < date_from:
                continue
            if date_to is not None and target_date > date_to:
                continue
            rows.append(target)

        rows.sort(
            key=lambda row: (str(row["target_date"]), int(row["id"])),
            reverse=True,
        )
        return self._copy(rows)

    async def get_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object] | None:
        """Return one daily target row for a subject and date."""

        row = self._subject_date_bucket(self.daily_targets, subject).get(target_date)
        return self._copy(row) if row is not None else None

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
        """Create or replace one daily target row for a subject and date."""

        bucket = self._subject_date_bucket(self.daily_targets, subject)
        row = bucket.get(target_date)
        now = self._timestamp()
        if row is None:
            row = {
                "id": self._next_id("target"),
                "subject": subject,
                "target_date": target_date,
                "created_at": now,
            }
            bucket[target_date] = row

        row.update(
            {
                "target_food_calories": target_food_calories,
                "target_exercise_calories": target_exercise_calories,
                "target_protein_g": target_protein_g,
                "target_carbs_g": target_carbs_g,
                "target_fat_g": target_fat_g,
                "notes_markdown": notes_markdown,
                "updated_at": now,
            }
        )
        return self._copy(row)

    async def delete_daily_target(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Delete one daily target row for a subject and date."""

        deleted = self._subject_date_bucket(self.daily_targets, subject).pop(
            target_date,
            None,
        )
        return {"deleted": deleted is not None, "target_date": target_date}

    async def list_daily_metrics(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        metric_type: str | None = None,
    ) -> list[dict[str, object]]:
        """List daily metrics owned by one subject.

        Parameters:
            subject: Stable row owner for the current caller.
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            metric_type: Optional supported metric type filter.

        Returns:
            list[dict[str, object]]: Copied fake metric rows.

        Raises:
            ValueError: If the metric type is unsupported.
        """

        normalized_type = (
            None if metric_type is None else self._normalize_metric_type(metric_type)
        )
        rows = []
        for metric in self._subject_date_bucket(self.daily_metrics, subject).values():
            metric_date = str(metric["metric_date"])
            if date_from is not None and metric_date < date_from:
                continue
            if date_to is not None and metric_date > date_to:
                continue
            if normalized_type is not None and metric["metric_type"] != normalized_type:
                continue
            rows.append(metric)

        rows.sort(
            key=lambda row: (
                str(row["metric_date"]),
                str(row["metric_type"]),
                int(row["id"]),
            ),
            reverse=True,
        )
        return self._copy(rows)

    async def get_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
    ) -> dict[str, object] | None:
        """Return one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric.
            metric_type: Supported metric type to read.

        Returns:
            dict[str, object] | None: Copied metric row, or `None` when missing.

        Raises:
            ValueError: If the metric type is unsupported.
        """

        normalized_type = self._normalize_metric_type(metric_type)
        key = f"{metric_date}:{normalized_type}"
        row = self._subject_date_bucket(self.daily_metrics, subject).get(key)
        return self._copy(row) if row is not None else None

    async def set_daily_metric(
        self,
        subject: str,
        metric_date: str,
        metric_type: str,
        value: float,
    ) -> dict[str, object]:
        """Create or replace one daily metric row for a subject, date, and type.

        Parameters:
            subject: Stable row owner for the current caller.
            metric_date: ISO calendar date for the metric.
            metric_type: Supported metric type to store.
            value: Numeric metric value validated by metric type.

        Returns:
            dict[str, object]: Copied upserted metric row.

        Raises:
            ValueError: If the metric type or value is invalid.
        """

        normalized_type = self._normalize_metric_type(metric_type)
        normalized_value = self._validate_metric_value(normalized_type, value)
        bucket = self._subject_date_bucket(self.daily_metrics, subject)
        key = f"{metric_date}:{normalized_type}"
        row = bucket.get(key)
        now = self._timestamp()
        if row is None:
            row = {
                "id": self._next_id("metric"),
                "subject": subject,
                "metric_date": metric_date,
                "metric_type": normalized_type,
                "created_at": now,
            }
            bucket[key] = row

        row.update(
            {
                "value": normalized_value,
                "updated_at": now,
            }
        )
        return self._copy(row)

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
            ValueError: If the metric type is unsupported.
        """

        normalized_type = self._normalize_metric_type(metric_type)
        key = f"{metric_date}:{normalized_type}"
        deleted = self._subject_date_bucket(self.daily_metrics, subject).pop(key, None)
        return {
            "deleted": deleted is not None,
            "metric_date": metric_date,
            "metric_type": normalized_type,
        }

    async def list_daily_meals(
        self,
        subject: str,
        meal_date: str | None = None,
    ) -> list[dict[str, object]]:
        """List meal headers for one subject."""

        rows = []
        for meal in self._subject_bucket(self.meals, subject).values():
            if meal_date is not None and meal["meal_date"] != meal_date:
                continue
            rows.append(meal)

        rows.sort(key=lambda row: (str(row["meal_date"]), int(row["id"])), reverse=True)
        return self._copy(rows)

    async def get_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object] | None:
        """Return one meal row for a subject."""

        row = self._subject_bucket(self.meals, subject).get(meal_id)
        return self._copy(row) if row is not None else None

    async def add_meal(
        self,
        subject: str,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object]:
        """Create one meal header for a subject."""

        now = self._timestamp()
        meal_id = self._next_id("meal")
        row = {
            "id": meal_id,
            "subject": subject,
            "meal_date": meal_date,
            "meal_label": meal_label,
            "notes_markdown": notes_markdown,
            "created_at": now,
            "updated_at": now,
        }
        self._subject_bucket(self.meals, subject)[meal_id] = row
        return self._copy(row)

    async def update_meal(
        self,
        subject: str,
        meal_id: int,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
    ) -> dict[str, object] | None:
        """Replace one meal header owned by a subject."""

        row = self._subject_bucket(self.meals, subject).get(meal_id)
        if row is None:
            return None

        row.update(
            {
                "meal_date": meal_date,
                "meal_label": meal_label,
                "notes_markdown": notes_markdown,
                "updated_at": self._timestamp(),
            }
        )
        return self._copy(row)

    async def delete_meal(
        self,
        subject: str,
        meal_id: int,
    ) -> dict[str, object]:
        """Delete one meal header and its child items."""

        deleted = self._subject_bucket(self.meals, subject).pop(meal_id, None)
        if deleted is not None:
            for item_id, item in list(
                self._subject_bucket(self.meal_items, subject).items()
            ):
                if item["meal_id"] == meal_id:
                    del self._subject_bucket(self.meal_items, subject)[item_id]
        return {"deleted": deleted is not None, "meal_id": meal_id}

    async def list_meal_items(
        self,
        subject: str,
        meal_id: int,
    ) -> list[dict[str, object]]:
        """List all meal items attached to one subject-owned meal."""

        self._get_meal_row(subject, meal_id)
        rows = [
            row
            for row in self._subject_bucket(self.meal_items, subject).values()
            if row["meal_id"] == meal_id
        ]
        rows.sort(key=lambda row: int(row["id"]))
        return self._copy(rows)

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
        """Create one meal item and update product usage for successful adds.

        Parameters:
            subject: Stable row owner for the current caller.
            meal_id: Parent meal identifier.
            grams: Consumed grams for the meal item.
            ingredient_name: Free-text ingredient name for manual items or
                optional custom label for catalog-based items.
            product_id: Optional catalog product identifier.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.

        Returns:
            dict[str, object]: Created in-memory meal item row.

        Raises:
            RuntimeError: If the meal or referenced product is invalid.
            ValueError: If the meal item data is incomplete or invalid.
        """

        self._get_meal_row(subject, meal_id)
        snapshot = self._build_meal_item_snapshot(
            subject=subject,
            product_id=product_id,
            ingredient_name=ingredient_name,
            grams=grams,
            calories=calories,
            carbs_g=carbs_g,
            protein_g=protein_g,
            fat_g=fat_g,
        )
        now = self._timestamp()
        meal_item_id = self._next_id("meal_item")
        row = {
            "id": meal_item_id,
            "subject": subject,
            "meal_id": meal_id,
            "product_id": product_id,
            "ingredient_name": snapshot["ingredient_name"],
            "grams": grams,
            "calories": snapshot["calories"],
            "carbs_g": snapshot["carbs_g"],
            "protein_g": snapshot["protein_g"],
            "fat_g": snapshot["fat_g"],
            "created_at": now,
            "updated_at": now,
        }
        self._subject_bucket(self.meal_items, subject)[meal_item_id] = row
        if product_id is not None:
            # Mirror the Postgres store: usage_count is internal bookkeeping for
            # successful product-backed additions, not a caller-managed field.
            product = self._get_product_row(subject, product_id)
            product["usage_count"] = int(product.get("usage_count", 0)) + 1

        return self._copy(row)

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

        row = self._subject_bucket(self.meal_items, subject).get(meal_item_id)
        if row is None:
            return None

        self._get_meal_row(subject, meal_id)
        snapshot = self._build_meal_item_snapshot(
            subject=subject,
            product_id=product_id,
            ingredient_name=ingredient_name,
            grams=grams,
            calories=calories,
            carbs_g=carbs_g,
            protein_g=protein_g,
            fat_g=fat_g,
        )
        row.update(
            {
                "meal_id": meal_id,
                "product_id": product_id,
                "ingredient_name": snapshot["ingredient_name"],
                "grams": grams,
                "calories": snapshot["calories"],
                "carbs_g": snapshot["carbs_g"],
                "protein_g": snapshot["protein_g"],
                "fat_g": snapshot["fat_g"],
                "updated_at": self._timestamp(),
            }
        )
        return self._copy(row)

    async def delete_meal_item(
        self,
        subject: str,
        meal_item_id: int,
    ) -> dict[str, object]:
        """Delete one meal item owned by a subject."""

        deleted = self._subject_bucket(self.meal_items, subject).pop(
            meal_item_id,
            None,
        )
        return {"deleted": deleted is not None, "meal_item_id": meal_item_id}

    async def list_activities(
        self,
        subject: str,
        date_from: str | None = None,
        date_to: str | None = None,
        external_source: str | None = None,
    ) -> list[dict[str, object]]:
        """List activity entries for one subject."""

        rows = []
        for activity in self._subject_bucket(self.activities, subject).values():
            activity_date = str(activity["activity_date"])
            if date_from is not None and activity_date < date_from:
                continue
            if date_to is not None and activity_date > date_to:
                continue
            if (
                external_source is not None
                and activity["external_source"] != external_source
            ):
                continue
            rows.append(activity)

        rows.sort(
            key=lambda row: (str(row["activity_date"]), int(row["id"])),
            reverse=True,
        )
        return self._copy(rows)

    async def get_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object] | None:
        """Return one activity row for a subject."""

        row = self._subject_bucket(self.activities, subject).get(activity_id)
        return self._copy(row) if row is not None else None

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

        now = self._timestamp()
        activity_id = self._next_id("activity")
        row = {
            "id": activity_id,
            "subject": subject,
            "activity_date": activity_date,
            "title": title,
            "external_source": external_source,
            "external_activity_id": external_activity_id,
            "athlete_id": athlete_id,
            "sport_type": sport_type,
            "distance_meters": distance_meters,
            "moving_time_seconds": moving_time_seconds,
            "elapsed_time_seconds": elapsed_time_seconds,
            "total_elevation_gain_meters": total_elevation_gain_meters,
            "average_speed_mps": average_speed_mps,
            "max_speed_mps": max_speed_mps,
            "average_heartrate": average_heartrate,
            "max_heartrate": max_heartrate,
            "average_watts": average_watts,
            "weighted_average_watts": weighted_average_watts,
            "calories": calories,
            "kilojoules": kilojoules,
            "suffer_score": suffer_score,
            "trainer": trainer,
            "commute": commute,
            "manual": manual,
            "is_private": is_private,
            "zones": zones,
            "laps": laps,
            "streams": streams,
            "raw_payload": raw_payload,
            "notes_markdown": notes_markdown,
            "created_at": now,
            "updated_at": now,
        }
        self._subject_bucket(self.activities, subject)[activity_id] = row
        return self._copy(row)

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

        row = self._subject_bucket(self.activities, subject).get(activity_id)
        if row is None:
            return None

        row.update(
            {
                "activity_date": activity_date,
                "title": title,
                "external_source": external_source,
                "external_activity_id": external_activity_id,
                "athlete_id": athlete_id,
                "sport_type": sport_type,
                "distance_meters": distance_meters,
                "moving_time_seconds": moving_time_seconds,
                "elapsed_time_seconds": elapsed_time_seconds,
                "total_elevation_gain_meters": total_elevation_gain_meters,
                "average_speed_mps": average_speed_mps,
                "max_speed_mps": max_speed_mps,
                "average_heartrate": average_heartrate,
                "max_heartrate": max_heartrate,
                "average_watts": average_watts,
                "weighted_average_watts": weighted_average_watts,
                "calories": calories,
                "kilojoules": kilojoules,
                "suffer_score": suffer_score,
                "trainer": trainer,
                "commute": commute,
                "manual": manual,
                "is_private": is_private,
                "zones": zones,
                "laps": laps,
                "streams": streams,
                "raw_payload": raw_payload,
                "notes_markdown": notes_markdown,
                "updated_at": self._timestamp(),
            }
        )
        return self._copy(row)

    async def upsert_external_activity(
        self,
        subject: str,
        activity: dict[str, object],
    ) -> dict[str, object]:
        """Insert or update one synced external activity row."""

        external_source = str(activity["external_source"])
        external_activity_id = str(activity["external_activity_id"])
        bucket = self._subject_bucket(self.activities, subject)
        existing_id = next(
            (
                activity_id
                for activity_id, row in bucket.items()
                if row["external_source"] == external_source
                and row["external_activity_id"] == external_activity_id
            ),
            None,
        )

        if existing_id is None:
            item = await self.add_activity(
                subject,
                activity_date=str(activity["activity_date"]),
                title=str(activity["title"]),
                external_source=external_source,
                external_activity_id=external_activity_id,
                athlete_id=activity.get("athlete_id"),  # type: ignore[arg-type]
                sport_type=activity.get("sport_type"),  # type: ignore[arg-type]
                distance_meters=activity.get("distance_meters"),  # type: ignore[arg-type]
                moving_time_seconds=activity.get("moving_time_seconds"),  # type: ignore[arg-type]
                elapsed_time_seconds=activity.get("elapsed_time_seconds"),  # type: ignore[arg-type]
                total_elevation_gain_meters=activity.get(
                    "total_elevation_gain_meters"
                ),  # type: ignore[arg-type]
                average_speed_mps=activity.get("average_speed_mps"),  # type: ignore[arg-type]
                max_speed_mps=activity.get("max_speed_mps"),  # type: ignore[arg-type]
                average_heartrate=activity.get("average_heartrate"),  # type: ignore[arg-type]
                max_heartrate=activity.get("max_heartrate"),  # type: ignore[arg-type]
                average_watts=activity.get("average_watts"),  # type: ignore[arg-type]
                weighted_average_watts=activity.get("weighted_average_watts"),  # type: ignore[arg-type]
                calories=activity.get("calories"),  # type: ignore[arg-type]
                kilojoules=activity.get("kilojoules"),  # type: ignore[arg-type]
                suffer_score=activity.get("suffer_score"),  # type: ignore[arg-type]
                trainer=bool(activity.get("trainer", False)),
                commute=bool(activity.get("commute", False)),
                manual=bool(activity.get("manual", False)),
                is_private=bool(activity.get("is_private", False)),
                zones=activity.get("zones"),  # type: ignore[arg-type]
                laps=activity.get("laps"),  # type: ignore[arg-type]
                streams=activity.get("streams"),  # type: ignore[arg-type]
                raw_payload=activity.get("raw_payload"),  # type: ignore[arg-type]
                notes_markdown=str(activity.get("notes_markdown") or ""),
            )
            return {"action": "inserted", "item": item}

        item = await self.update_activity(
            subject,
            activity_id=existing_id,
            activity_date=str(activity["activity_date"]),
            title=str(activity["title"]),
            external_source=external_source,
            external_activity_id=external_activity_id,
            athlete_id=activity.get("athlete_id"),  # type: ignore[arg-type]
            sport_type=activity.get("sport_type"),  # type: ignore[arg-type]
            distance_meters=activity.get("distance_meters"),  # type: ignore[arg-type]
            moving_time_seconds=activity.get("moving_time_seconds"),  # type: ignore[arg-type]
            elapsed_time_seconds=activity.get("elapsed_time_seconds"),  # type: ignore[arg-type]
            total_elevation_gain_meters=activity.get(
                "total_elevation_gain_meters"
            ),  # type: ignore[arg-type]
            average_speed_mps=activity.get("average_speed_mps"),  # type: ignore[arg-type]
            max_speed_mps=activity.get("max_speed_mps"),  # type: ignore[arg-type]
            average_heartrate=activity.get("average_heartrate"),  # type: ignore[arg-type]
            max_heartrate=activity.get("max_heartrate"),  # type: ignore[arg-type]
            average_watts=activity.get("average_watts"),  # type: ignore[arg-type]
            weighted_average_watts=activity.get("weighted_average_watts"),  # type: ignore[arg-type]
            calories=activity.get("calories"),  # type: ignore[arg-type]
            kilojoules=activity.get("kilojoules"),  # type: ignore[arg-type]
            suffer_score=activity.get("suffer_score"),  # type: ignore[arg-type]
            trainer=bool(activity.get("trainer", False)),
            commute=bool(activity.get("commute", False)),
            manual=bool(activity.get("manual", False)),
            is_private=bool(activity.get("is_private", False)),
            zones=activity.get("zones"),  # type: ignore[arg-type]
            laps=activity.get("laps"),  # type: ignore[arg-type]
            streams=activity.get("streams"),  # type: ignore[arg-type]
            raw_payload=activity.get("raw_payload"),  # type: ignore[arg-type]
            notes_markdown=str(activity.get("notes_markdown") or ""),
        )
        return {"action": "updated", "item": item}

    async def get_external_service_token(
        self,
        subject: str,
        service: str,
    ) -> dict[str, object] | None:
        """Return a stored external service token for one subject."""

        row = self.external_tokens.get(subject, {}).get(service)
        return self._copy(row) if row is not None else None

    async def save_external_service_token(
        self,
        subject: str,
        service: str,
        access_token: str | None,
        refresh_token: str,
        expires_at: int | None,
        raw_payload: dict[str, object],
    ) -> dict[str, object]:
        """Store the latest external service token for one subject."""

        now = self._timestamp()
        row = {
            "subject": subject,
            "service": service,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "raw_payload": raw_payload,
            "created_at": now,
            "updated_at": now,
        }
        self.external_tokens.setdefault(subject, {})[service] = row
        return self._copy(row)

    async def delete_activity(
        self,
        subject: str,
        activity_id: int,
    ) -> dict[str, object]:
        """Delete one activity entry owned by a subject."""

        deleted = self._subject_bucket(self.activities, subject).pop(activity_id, None)
        return {"deleted": deleted is not None, "activity_id": activity_id}

    async def list_memory_items(
        self,
        subject: str,
        category: str | None = None,
    ) -> list[dict[str, object]]:
        """List long-term memory items for one subject."""

        rows = []
        for item in self._subject_bucket(self.memory_items, subject).values():
            if category is not None and item["category"] != category:
                continue
            rows.append(item)

        rows.sort(
            key=lambda row: (str(row["created_at"]), int(row["id"])),
            reverse=True,
        )
        return self._copy(rows)

    async def get_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object] | None:
        """Return one long-term memory row for a subject."""

        row = self._subject_bucket(self.memory_items, subject).get(memory_item_id)
        return self._copy(row) if row is not None else None

    async def add_memory_item(
        self,
        subject: str,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object]:
        """Create one long-term memory item for a subject."""

        now = self._timestamp()
        memory_item_id = self._next_id("memory")
        row = {
            "id": memory_item_id,
            "subject": subject,
            "title": title,
            "category": category,
            "content_markdown": content_markdown,
            "created_at": now,
            "updated_at": now,
        }
        self._subject_bucket(self.memory_items, subject)[memory_item_id] = row
        return self._copy(row)

    async def update_memory_item(
        self,
        subject: str,
        memory_item_id: int,
        title: str,
        content_markdown: str,
        category: str | None = None,
    ) -> dict[str, object] | None:
        """Replace one long-term memory item owned by a subject."""

        row = self._subject_bucket(self.memory_items, subject).get(memory_item_id)
        if row is None:
            return None

        row.update(
            {
                "title": title,
                "category": category,
                "content_markdown": content_markdown,
                "updated_at": self._timestamp(),
            }
        )
        return self._copy(row)

    async def delete_memory_item(
        self,
        subject: str,
        memory_item_id: int,
    ) -> dict[str, object]:
        """Delete one long-term memory item owned by a subject."""

        deleted = self._subject_bucket(self.memory_items, subject).pop(
            memory_item_id,
            None,
        )
        return {"deleted": deleted is not None, "memory_item_id": memory_item_id}

    async def get_daily_summary(
        self,
        subject: str,
        target_date: str,
    ) -> dict[str, object]:
        """Compute the target-vs-actual summary for one subject and date."""

        target_row = self._subject_date_bucket(self.daily_targets, subject).get(
            target_date
        )
        meals = [
            meal
            for meal in self._subject_bucket(self.meals, subject).values()
            if meal["meal_date"] == target_date
        ]
        meal_ids = {int(meal["id"]) for meal in meals}
        meal_items = [
            item
            for item in self._subject_bucket(self.meal_items, subject).values()
            if int(item["meal_id"]) in meal_ids
        ]
        activities = [
            activity
            for activity in self._subject_bucket(self.activities, subject).values()
            if activity["activity_date"] == target_date
        ]

        actual_food_calories = round(
            sum(float(item["calories"]) for item in meal_items),
            2,
        )
        actual_exercise_calories = round(
            sum(float(activity["calories"] or 0) for activity in activities),
            2,
        )
        actual_protein_g = round(
            sum(float(item["protein_g"]) for item in meal_items),
            2,
        )
        actual_carbs_g = round(
            sum(float(item["carbs_g"]) for item in meal_items),
            2,
        )
        actual_fat_g = round(
            sum(float(item["fat_g"]) for item in meal_items),
            2,
        )

        return {
            "target_date": target_date,
            "target_food_calories": (
                None
                if target_row is None
                else target_row["target_food_calories"]
            ),
            "target_exercise_calories": None
            if target_row is None
            else target_row["target_exercise_calories"],
            "target_protein_g": (
                None if target_row is None else target_row["target_protein_g"]
            ),
            "target_carbs_g": (
                None if target_row is None else target_row["target_carbs_g"]
            ),
            "target_fat_g": None if target_row is None else target_row["target_fat_g"],
            "actual_food_calories": actual_food_calories,
            "actual_exercise_calories": actual_exercise_calories,
            "actual_protein_g": actual_protein_g,
            "actual_carbs_g": actual_carbs_g,
            "actual_fat_g": actual_fat_g,
            "net_calories": round(actual_food_calories - actual_exercise_calories, 2),
            "meals_count": len(meals),
            "meal_items_count": len(meal_items),
            "activities_count": len(activities),
        }

    async def close(self) -> None:
        """Release fake resources.

        Parameters:
            None.

        Returns:
            None.
        """


@pytest.fixture
def no_auth_settings() -> Settings:
    """Return test settings that keep the server in local no-auth mode.

    Parameters:
        None.

    Returns:
        Settings: Local configuration for in-process tests.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


@pytest.fixture
def bearer_settings() -> Settings:
    """Return test settings that protect the HTTP server with a bearer token.

    Parameters:
        None.

    Returns:
        Settings: Configuration that requires `MCP_API_TOKEN`.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="bearer",
        api_token="top-secret-token",
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


@pytest.fixture
def oauth_settings() -> Settings:
    """Return test settings that enable OAuth production mode.

    Parameters:
        None.

    Returns:
        Settings: OAuth settings for construction tests.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="oauth",
        api_token=None,
        public_base_url="https://example.com",
        workos_authkit_domain="https://demo.authkit.app",
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )


def make_httpx_client_factory(app: Any) -> Callable[..., httpx.AsyncClient]:
    """Create an httpx client factory that targets an in-process ASGI app.

    Parameters:
        app: ASGI application returned by `FastMCP.http_app(...)`.

    Returns:
        Callable[..., httpx.AsyncClient]: Factory compatible with FastMCP's
            HTTP transport hooks.
    """

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        """Construct an AsyncClient that routes requests into the ASGI app.

        Parameters:
            **kwargs: Client options forwarded by FastMCP's HTTP transport.

        Returns:
            httpx.AsyncClient: Client backed by `httpx.ASGITransport`.
        """

        kwargs.setdefault("base_url", "http://testserver")
        kwargs["transport"] = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(**kwargs)

    return factory


def initialize_payload() -> dict[str, object]:
    """Return a minimal MCP initialize request body for HTTP auth tests.

    Parameters:
        None.

    Returns:
        dict[str, object]: JSON-RPC payload accepted by the MCP endpoint.
    """

    return {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "pytest-client", "version": "0.1.0"},
        },
    }


def as_mapping(payload: object) -> dict[str, object]:
    """Normalize FastMCP object payloads into plain dictionaries for asserts.

    Parameters:
        payload: Raw tool result payload returned by the FastMCP client.

    Returns:
        dict[str, object]: Plain dictionary representation of the payload.
    """

    if isinstance(payload, dict):
        return payload
    return dict(vars(payload))


def as_mapping_list(payload: object) -> list[dict[str, object]]:
    """Normalize a list of FastMCP object payloads into plain dictionaries.

    Parameters:
        payload: Raw tool result payload returned by the FastMCP client.

    Returns:
        list[dict[str, object]]: Plain dictionary rows for assertions.
    """

    return [as_mapping(item) for item in list(payload)]


def test_server_can_be_constructed_in_oauth_mode(
    monkeypatch,
    oauth_settings: Settings,
) -> None:
    """Ensure server assembly works when OAuth mode is selected.

    Parameters:
        monkeypatch: Pytest fixture for patching auth provider creation.
        oauth_settings: OAuth settings fixture for server construction.

    Returns:
        None.
    """

    sentinel = object()

    def fake_build_auth_provider(settings: Settings) -> object:
        """Return a sentinel provider so server construction stays offline.

        Parameters:
            settings: Runtime settings passed from the server factory.

        Returns:
            object: Sentinel auth provider used for assertions.
        """

        assert settings is oauth_settings
        return sentinel

    monkeypatch.setattr(
        "apex_mcp_server.server.build_auth_provider",
        fake_build_auth_provider,
    )

    server = create_mcp_server(settings=oauth_settings, store=InMemoryUserStore())

    assert server.name == "APEX FastMCP Profile Pilot"


@pytest.mark.asyncio
async def test_server_tools_cover_singletons_collections_and_summary(
    no_auth_settings: Settings,
) -> None:
    """Exercise the grouped MCP surface across singleton, CRUD, and summary tools.

    Parameters:
        no_auth_settings: Local test settings.

    Returns:
        None.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        published_tools = await client.list_tools()
        tool_names = {tool.name for tool in published_tools}

        initial_profile = await client.call_tool(
            "profile_documents",
            {"operation": "get", "document": "profile"},
        )
        initial_user_data = await client.call_tool(
            "user_data",
            {"operation": "get"},
        )

        await client.call_tool(
            "profile_documents",
            {
                "operation": "set",
                "document": "profile",
                "markdown": "# Runner Persona\nWarm and practical.",
            },
        )
        await client.call_tool(
            "user_data",
            {
                "operation": "set",
                "weight_kg": 68.5,
                "height_cm": 174.0,
                "ftp_watts": 250,
            },
        )
        await client.call_tool(
            "profile_documents",
            {
                "operation": "set",
                "document": "diet_preferences",
                "markdown": "Prefer Mediterranean-style meals.",
            },
        )
        await client.call_tool(
            "profile_documents",
            {
                "operation": "set",
                "document": "diet_goals",
                "markdown": "Aim for 0.5 kg/week fat loss.",
            },
        )
        await client.call_tool(
            "profile_documents",
            {
                "operation": "set",
                "document": "training_goals",
                "markdown": "Build FTP and keep long rides consistent.",
            },
        )

        product = await client.call_tool(
            "products",
            {
                "operation": "add",
                "name": "Oats",
                "default_serving_g": 60.0,
                "calories_per_100g": 389.0,
                "carbs_g_per_100g": 66.0,
                "protein_g_per_100g": 17.0,
                "fat_g_per_100g": 7.0,
                "notes_markdown": "Breakfast staple",
            },
        )
        product_data = as_mapping(product.data)["item"]
        listed_products = await client.call_tool("products", {"operation": "list"})
        loaded_product = await client.call_tool(
            "products",
            {"operation": "get", "product_id": product_data["id"]},
        )
        updated_product = await client.call_tool(
            "products",
            {
                "operation": "update",
                "product_id": product_data["id"],
                "name": "Rolled oats",
                "default_serving_g": 70.0,
                "calories_per_100g": 389.0,
                "carbs_g_per_100g": 66.0,
                "protein_g_per_100g": 17.0,
                "fat_g_per_100g": 7.0,
                "notes_markdown": "Updated note",
            },
        )

        daily_target = await client.call_tool(
            "daily_targets",
            {
                "operation": "set",
                "target_date": "2026-04-14",
                "target_food_calories": 2200.0,
                "target_exercise_calories": 700.0,
                "target_protein_g": 150.0,
                "target_carbs_g": 250.0,
                "target_fat_g": 60.0,
                "notes_markdown": "Long ride day",
            },
        )
        daily_target_data = as_mapping(daily_target.data)["item"]
        listed_targets = await client.call_tool(
            "daily_targets",
            {"operation": "list"},
        )
        loaded_target = await client.call_tool(
            "daily_targets",
            {"operation": "get", "target_date": "2026-04-14"},
        )

        daily_metric = await client.call_tool(
            "daily_metrics",
            {
                "operation": "set",
                "metric_date": "2026-04-14",
                "metric_type": " Weight ",
                "value": 68.5,
            },
        )
        daily_metric_data = as_mapping(daily_metric.data)["item"]
        updated_daily_metric = await client.call_tool(
            "daily_metrics",
            {
                "operation": "set",
                "metric_date": "2026-04-14",
                "metric_type": "weight",
                "value": 69.0,
            },
        )
        await client.call_tool(
            "daily_metrics",
            {
                "operation": "set",
                "metric_date": "2026-04-14",
                "metric_type": "steps",
                "value": 12000.0,
            },
        )
        listed_daily_metrics = await client.call_tool(
            "daily_metrics",
            {
                "operation": "list",
                "date_from": "2026-04-14",
                "date_to": "2026-04-14",
            },
        )
        listed_weight_metrics = await client.call_tool(
            "daily_metrics",
            {"operation": "list", "metric_type": "weight"},
        )
        loaded_daily_metric = await client.call_tool(
            "daily_metrics",
            {
                "operation": "get",
                "metric_date": "2026-04-14",
                "metric_type": "WEIGHT",
            },
        )

        meal = await client.call_tool(
            "meals",
            {
                "operation": "add",
                "meal_date": "2026-04-14",
                "meal_label": "Breakfast",
                "notes_markdown": "Pre-ride meal",
            },
        )
        meal_data = as_mapping(meal.data)["item"]
        listed_meals = await client.call_tool(
            "meals",
            {"operation": "list", "meal_date": "2026-04-14"},
        )
        loaded_meal = await client.call_tool(
            "meals",
            {"operation": "get", "meal_id": meal_data["id"]},
        )
        updated_meal = await client.call_tool(
            "meals",
            {
                "operation": "update",
                "meal_id": meal_data["id"],
                "meal_date": "2026-04-14",
                "meal_label": "Breakfast updated",
                "notes_markdown": "Updated notes",
            },
        )

        meal_item = await client.call_tool(
            "meal_items",
            {
                "operation": "add",
                "meal_id": meal_data["id"],
                "product_id": product_data["id"],
                "grams": 80.0,
            },
        )
        meal_item_data = as_mapping(meal_item.data)["item"]
        product_after_meal_item = await client.call_tool(
            "products",
            {"operation": "get", "product_id": product_data["id"]},
        )
        products_after_meal_item = await client.call_tool(
            "products",
            {"operation": "list"},
        )
        listed_meal_items = await client.call_tool(
            "meal_items",
            {"operation": "list", "meal_id": meal_data["id"]},
        )
        updated_meal_item = await client.call_tool(
            "meal_items",
            {
                "operation": "update",
                "meal_item_id": meal_item_data["id"],
                "meal_id": meal_data["id"],
                "product_id": product_data["id"],
                "grams": 90.0,
            },
        )

        activity = await client.call_tool(
            "activities",
            {
                "operation": "add",
                "activity_date": "2026-04-14",
                "title": "Morning ride",
                "external_source": "strava",
                "external_activity_id": "ride-1",
                "sport_type": "Ride",
                "calories": 650.0,
                "distance_meters": 54000.0,
                "zones": {"z2": 80},
                "laps": [{"lap": 1, "seconds": 600}],
                "streams": {"heartrate": [120, 130]},
                "raw_payload": {"provider": "demo"},
            },
        )
        activity_data = as_mapping(activity.data)["item"]
        listed_activities = await client.call_tool(
            "activities",
            {
                "operation": "list",
                "date_from": "2026-04-14",
                "date_to": "2026-04-14",
            },
        )
        loaded_activity = await client.call_tool(
            "activities",
            {"operation": "get", "activity_id": activity_data["id"]},
        )
        updated_activity = await client.call_tool(
            "activities",
            {
                "operation": "update",
                "activity_id": activity_data["id"],
                "activity_date": "2026-04-14",
                "title": "Morning ride updated",
                "external_source": "strava",
                "external_activity_id": "ride-1",
                "sport_type": "Ride",
                "calories": 700.0,
                "manual": False,
                "zones": {"z2": 90},
            },
        )

        memory_item = await client.call_tool(
            "memory_items",
            {
                "operation": "add",
                "title": "Fueling preference",
                "content_markdown": "Prefers gels after 90 minutes.",
                "category": "nutrition",
            },
        )
        memory_item_data = as_mapping(memory_item.data)["item"]
        listed_memory_items = await client.call_tool(
            "memory_items",
            {"operation": "list", "category": "nutrition"},
        )
        loaded_memory_item = await client.call_tool(
            "memory_items",
            {"operation": "get", "memory_item_id": memory_item_data["id"]},
        )
        updated_memory_item = await client.call_tool(
            "memory_items",
            {
                "operation": "update",
                "memory_item_id": memory_item_data["id"],
                "title": "Fueling preference updated",
                "content_markdown": "Prefers gels after 75 minutes.",
                "category": "nutrition",
            },
        )

        summary = await client.call_tool(
            "get_daily_summary",
            {"target_date": "2026-04-14"},
        )
        updated_profile = await client.call_tool(
            "profile_documents",
            {"operation": "get", "document": "profile"},
        )
        updated_user_data = await client.call_tool("user_data", {"operation": "get"})
        diet_preferences = await client.call_tool(
            "profile_documents",
            {"operation": "get", "document": "diet_preferences"},
        )
        diet_goals = await client.call_tool(
            "profile_documents",
            {"operation": "get", "document": "diet_goals"},
        )
        training_goals = await client.call_tool(
            "profile_documents",
            {"operation": "get", "document": "training_goals"},
        )
        whoami_result = await client.call_tool("whoami")
        resource_result = await client.read_resource("profile://me")
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Write a short training reminder."},
        )
        deleted_meal_item = await client.call_tool(
            "meal_items",
            {"operation": "delete", "meal_item_id": meal_item_data["id"]},
        )
        deleted_meal = await client.call_tool(
            "meals",
            {"operation": "delete", "meal_id": meal_data["id"]},
        )
        deleted_target = await client.call_tool(
            "daily_targets",
            {"operation": "delete", "target_date": "2026-04-14"},
        )
        deleted_daily_metric = await client.call_tool(
            "daily_metrics",
            {
                "operation": "delete",
                "metric_date": "2026-04-14",
                "metric_type": "weight",
            },
        )
        deleted_activity = await client.call_tool(
            "activities",
            {"operation": "delete", "activity_id": activity_data["id"]},
        )
        deleted_memory = await client.call_tool(
            "memory_items",
            {"operation": "delete", "memory_item_id": memory_item_data["id"]},
        )
        deleted_product = await client.call_tool(
            "products",
            {"operation": "delete", "product_id": product_data["id"]},
        )

    listed_products_data = as_mapping(listed_products.data)["items"]
    loaded_product_data = as_mapping(loaded_product.data)["item"]
    updated_product_data = as_mapping(updated_product.data)["item"]
    product_after_meal_item_data = as_mapping(product_after_meal_item.data)["item"]
    products_after_meal_item_data = as_mapping(products_after_meal_item.data)["items"]
    listed_targets_data = as_mapping(listed_targets.data)["items"]
    loaded_target_data = as_mapping(loaded_target.data)["item"]
    updated_daily_metric_data = as_mapping(updated_daily_metric.data)["item"]
    listed_daily_metrics_data = as_mapping(listed_daily_metrics.data)["items"]
    listed_weight_metrics_data = as_mapping(listed_weight_metrics.data)["items"]
    loaded_daily_metric_data = as_mapping(loaded_daily_metric.data)["item"]
    listed_meals_data = as_mapping(listed_meals.data)["items"]
    loaded_meal_data = as_mapping(loaded_meal.data)["item"]
    updated_meal_data = as_mapping(updated_meal.data)["item"]
    listed_meal_items_data = as_mapping(listed_meal_items.data)["items"]
    updated_meal_item_data = as_mapping(updated_meal_item.data)["item"]
    listed_activities_data = as_mapping(listed_activities.data)["items"]
    loaded_activity_data = as_mapping(loaded_activity.data)["item"]
    updated_activity_data = as_mapping(updated_activity.data)["item"]
    listed_memory_items_data = as_mapping(listed_memory_items.data)["items"]
    loaded_memory_item_data = as_mapping(loaded_memory_item.data)["item"]
    updated_memory_item_data = as_mapping(updated_memory_item.data)["item"]
    summary_data = as_mapping(summary.data)
    initial_profile_data = as_mapping(initial_profile.data)
    initial_user_data_data = as_mapping(initial_user_data.data)
    updated_profile_data = as_mapping(updated_profile.data)
    updated_user_data_data = as_mapping(updated_user_data.data)
    diet_preferences_data = as_mapping(diet_preferences.data)
    diet_goals_data = as_mapping(diet_goals.data)
    training_goals_data = as_mapping(training_goals.data)

    assert tool_names == {
        "profile_documents",
        "user_data",
        "products",
        "daily_targets",
        "daily_metrics",
        "meals",
        "meal_items",
        "activities",
        "sync_external_service",
        "memory_items",
        "get_daily_summary",
        "whoami",
    }
    assert len(tool_names) <= 20
    assert initial_profile_data == {
        "operation": "get",
        "document": "profile",
        "markdown": "",
    }
    assert initial_user_data_data == {
        "operation": "get",
        "weight_kg": None,
        "height_cm": None,
        "ftp_watts": None,
    }
    assert updated_profile_data == {
        "operation": "get",
        "document": "profile",
        "markdown": "# Runner Persona\nWarm and practical.",
    }
    assert updated_user_data_data == {
        "operation": "get",
        "weight_kg": 68.5,
        "height_cm": 174.0,
        "ftp_watts": 250,
    }
    assert diet_preferences_data["markdown"] == "Prefer Mediterranean-style meals."
    assert diet_goals_data["markdown"] == "Aim for 0.5 kg/week fat loss."
    assert (
        training_goals_data["markdown"]
        == "Build FTP and keep long rides consistent."
    )
    assert listed_products_data[0]["name"] == "Oats"
    assert product_data["usage_count"] == 0
    assert listed_products_data[0]["usage_count"] == 0
    assert loaded_product_data["name"] == "Oats"
    assert loaded_product_data["usage_count"] == 0
    assert updated_product_data["name"] == "Rolled oats"
    assert updated_product_data["usage_count"] == 0
    assert product_after_meal_item_data["usage_count"] == 1
    assert products_after_meal_item_data[0]["usage_count"] == 1
    assert daily_target_data["target_date"] == "2026-04-14"
    assert listed_targets_data[0]["target_date"] == "2026-04-14"
    assert loaded_target_data["target_food_calories"] == 2200.0
    assert updated_daily_metric_data["id"] == daily_metric_data["id"]
    assert updated_daily_metric_data["metric_type"] == "weight"
    assert updated_daily_metric_data["value"] == 69.0
    assert {item["metric_type"] for item in listed_daily_metrics_data} == {
        "steps",
        "weight",
    }
    assert listed_weight_metrics_data[0]["value"] == 69.0
    assert loaded_daily_metric_data["value"] == 69.0
    assert listed_meals_data[0]["meal_label"] == "Breakfast"
    assert loaded_meal_data["meal_label"] == "Breakfast"
    assert updated_meal_data["meal_label"] == "Breakfast updated"
    assert listed_meal_items_data[0]["ingredient_name"] == "Rolled oats"
    assert updated_meal_item_data["grams"] == 90.0
    assert listed_activities_data[0]["title"] == "Morning ride"
    assert loaded_activity_data["external_source"] == "strava"
    assert updated_activity_data["title"] == "Morning ride updated"
    assert listed_memory_items_data[0]["title"] == "Fueling preference"
    assert loaded_memory_item_data["category"] == "nutrition"
    assert updated_memory_item_data["title"] == "Fueling preference updated"
    assert summary_data["target_date"] == "2026-04-14"
    assert summary_data["activities_count"] == 1
    assert summary_data["meal_items_count"] == 1
    assert summary_data["actual_food_calories"] > 0
    assert summary_data["actual_exercise_calories"] == 700.0
    assert whoami_result.data == {
        "authenticated": False,
        "subject": None,
        "login": None,
        "request_id": whoami_result.data["request_id"],
    }
    assert resource_result[0].text == "# Runner Persona\nWarm and practical."
    assert "Write a short training reminder." in prompt_result.messages[0].content.text
    assert (
        "# Runner Persona\nWarm and practical."
        in prompt_result.messages[0].content.text
    )
    assert prompt_result.meta == {"has_profile": True}
    assert as_mapping(deleted_meal_item.data) == {
        "operation": "delete",
        "deleted": True,
        "meal_item_id": meal_item_data["id"],
    }
    assert as_mapping(deleted_meal.data) == {
        "operation": "delete",
        "deleted": True,
        "meal_id": meal_data["id"],
    }
    assert as_mapping(deleted_target.data) == {
        "operation": "delete",
        "deleted": True,
        "target_date": "2026-04-14",
    }
    assert as_mapping(deleted_daily_metric.data) == {
        "operation": "delete",
        "deleted": True,
        "metric_date": "2026-04-14",
        "metric_type": "weight",
    }
    assert as_mapping(deleted_activity.data) == {
        "operation": "delete",
        "deleted": True,
        "activity_id": activity_data["id"],
    }
    assert as_mapping(deleted_memory.data) == {
        "operation": "delete",
        "deleted": True,
        "memory_item_id": memory_item_data["id"],
    }
    assert as_mapping(deleted_product.data) == {
        "operation": "delete",
        "deleted": True,
        "product_id": product_data["id"],
    }


@pytest.mark.asyncio
async def test_sync_external_service_tool_returns_summary(
    monkeypatch,
    no_auth_settings: Settings,
) -> None:
    """Ensure the external sync MCP tool delegates and returns its summary.

    Parameters:
        monkeypatch: Pytest fixture for replacing the network sync helper.
        no_auth_settings: Local test settings.

    Returns:
        None.
    """

    async def fake_run_sync(
        settings: Settings,
        store: UserStore,
        subject: str,
        service: str,
        day: str,
    ) -> dict[str, object]:
        """Return a stable sync summary without calling external services.

        Parameters:
            settings: Runtime settings passed by the MCP tool.
            store: Store passed by the MCP tool.
            subject: Resolved storage subject for the caller.
            service: Requested external service.
            day: Requested day.

        Returns:
            dict[str, object]: Fake sync summary.
        """

        assert settings is no_auth_settings
        assert isinstance(store, InMemoryUserStore)
        assert subject == "anonymous"
        assert service == "strava"
        assert day == "today"
        return {
            "service": "strava",
            "requested_day": "today",
            "resolved_date": "2026-04-29",
            "fetched_count": 1,
            "inserted_count": 1,
            "updated_count": 0,
            "skipped_count": 0,
            "activity_ids": [1],
            "warnings": [],
        }

    monkeypatch.setattr("apex_mcp_server.server.run_sync", fake_run_sync)
    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        result = await client.call_tool(
            "sync_external_service",
            {"service": "strava", "day": "today"},
        )

    assert as_mapping(result.data) == {
        "service": "strava",
        "requested_day": "today",
        "resolved_date": "2026-04-29",
        "fetched_count": 1,
        "inserted_count": 1,
        "updated_count": 0,
        "skipped_count": 0,
        "activity_ids": [1],
        "warnings": [],
    }


@pytest.mark.asyncio
async def test_daily_metrics_tool_reports_validation_errors(
    no_auth_settings: Settings,
) -> None:
    """Ensure invalid daily metric calls surface clear tool errors.

    Parameters:
        no_auth_settings: Local test settings.

    Returns:
        None.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        with pytest.raises(ToolError, match="Unsupported metric_type"):
            await client.call_tool(
                "daily_metrics",
                {
                    "operation": "set",
                    "metric_date": "2026-04-14",
                    "metric_type": "mood",
                    "value": 5.0,
                },
            )

        with pytest.raises(ToolError, match="steps value must be a whole number"):
            await client.call_tool(
                "daily_metrics",
                {
                    "operation": "set",
                    "metric_date": "2026-04-14",
                    "metric_type": "steps",
                    "value": 123.5,
                },
            )


@pytest.mark.asyncio
async def test_prompt_reports_missing_profile(no_auth_settings: Settings) -> None:
    """Ensure the prompt includes the empty-profile fallback text.

    Parameters:
        no_auth_settings: Local test settings.

    Returns:
        None.
    """

    server = create_mcp_server(
        settings=no_auth_settings,
        store=InMemoryUserStore(),
    )

    async with Client(server) as client:
        prompt_result = await client.get_prompt(
            "use_profile",
            {"task": "Draft an intro message."},
        )

    assert "No profile is saved yet for this caller." in prompt_result.messages[
        0
    ].content.text
    assert prompt_result.meta == {"has_profile": False}


@pytest.mark.asyncio
async def test_bearer_http_app_requires_authorization_header(
    bearer_settings: Settings,
) -> None:
    """Ensure the HTTP transport rejects requests without the shared token.

    Parameters:
        bearer_settings: Bearer-protected settings fixture.

    Returns:
        None.
    """

    server = create_mcp_server(
        settings=bearer_settings,
        store=InMemoryUserStore(),
    )
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post("/mcp", json=initialize_payload())

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_bearer_http_transport_accepts_valid_authorization_header(
    bearer_settings: Settings,
) -> None:
    """Ensure the HTTP transport initializes successfully with the token.

    Parameters:
        bearer_settings: Bearer-protected settings fixture.

    Returns:
        None.
    """

    server = create_mcp_server(
        settings=bearer_settings,
        store=InMemoryUserStore(),
    )
    app = server.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
    )
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
            headers={
                "Authorization": "Bearer top-secret-token",
                "Accept": "application/json, text/event-stream",
            },
        ) as client:
            response = await client.post("/mcp", json=initialize_payload())

    assert response.status_code == 200
    assert "APEX FastMCP Profile Pilot" in response.text
