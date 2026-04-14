"""FastMCP server assembly for the wellness pilot."""

from __future__ import annotations

from typing import Any

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.prompts import Message, PromptResult

from apex_mcp_server.auth import build_auth_provider
from apex_mcp_server.config import Settings
from apex_mcp_server.identity import resolve_identity
from apex_mcp_server.models import (
    ActivityRecord,
    DailySummaryRecord,
    DailyTargetRecord,
    MealItemRecord,
    MealRecord,
    MemoryItemRecord,
    ProductRecord,
    UserData,
    UserIdentity,
)
from apex_mcp_server.storage import UserStore, build_user_store

CURRENT_CONTEXT = CurrentContext()


def _resolve_request_identity(ctx: Context, auth_mode: str) -> UserIdentity:
    """Resolve the current caller identity for a tool, resource, or prompt.

    Parameters:
        ctx: Current FastMCP request context injected automatically.
        auth_mode: Active auth mode configured for the server.

    Returns:
        UserIdentity: Normalized identity used to scope storage operations.

    Raises:
        RuntimeError: If authentication is required but unavailable.
    """

    return resolve_identity(ctx, auth_mode)


def create_mcp_server(
    settings: Settings | None = None,
    store: UserStore | None = None,
) -> FastMCP:
    """Create the FastMCP server with tools, resource, and prompt.

    Parameters:
        settings: Optional pre-built runtime settings.
        store: Optional store override, mainly useful in tests.

    Returns:
        FastMCP: A fully configured MCP server instance.

    Raises:
        SettingsError: Propagated if runtime settings are invalid.
        ValueError: Propagated if FastMCP rejects server configuration.

    Example:
        >>> server = create_mcp_server()
        >>> server.name
        'APEX FastMCP Profile Pilot'
    """

    resolved_settings = settings or Settings.from_env()
    resolved_store = store or build_user_store(resolved_settings)

    mcp = FastMCP(
        name=resolved_settings.app_name,
        version=resolved_settings.version,
        instructions=(
            "A small FastMCP wellness pilot that stores markdown profile "
            "documents, numeric user data, food catalog records, daily logs, "
            "activity entries, and long-term memory in Postgres."
        ),
        auth=build_auth_provider(resolved_settings),
    )

    def current_identity(ctx: Context) -> UserIdentity:
        """Resolve the current caller identity for the active request.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            UserIdentity: Identity used to scope storage operations.

        Raises:
            RuntimeError: If authentication is required but unavailable.
        """

        return _resolve_request_identity(ctx, resolved_settings.auth_mode)

    @mcp.tool
    async def get_profile(ctx: Context = CURRENT_CONTEXT) -> str:
        """Return the caller's current profile markdown.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored profile markdown, or an empty string when no profile has
                been saved yet.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_profile(identity.storage_subject())

    @mcp.tool
    async def set_profile(
        profile_markdown: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's current profile markdown.

        Parameters:
            profile_markdown: New markdown content for the profile document.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation including `saved`, `subject`,
                and `bytes`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        result = await resolved_store.set_profile(
            identity.storage_subject(),
            profile_markdown,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def get_user_data(ctx: Context = CURRENT_CONTEXT) -> dict[str, object]:
        """Return the caller's saved numeric user data.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Numeric user fields with nullable values.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        data = await resolved_store.get_user_data(identity.storage_subject())
        return data.as_dict()

    @mcp.tool
    async def set_user_data(
        weight_kg: float | None,
        height_cm: float | None,
        ftp_watts: int | None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's saved numeric user data.

        Parameters:
            weight_kg: Body weight in kilograms, or `null`.
            height_cm: Height in centimeters, or `null`.
            ftp_watts: Functional threshold power in watts, or `null`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation plus the stored numeric values.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        data = UserData(
            weight_kg=weight_kg,
            height_cm=height_cm,
            ftp_watts=ftp_watts,
        )
        result = await resolved_store.set_user_data(
            identity.storage_subject(),
            data,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def get_diet_preferences(ctx: Context = CURRENT_CONTEXT) -> str:
        """Return the caller's saved diet-preferences markdown.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored markdown, or an empty string when no preferences have
                been saved yet.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_diet_preferences(identity.storage_subject())

    @mcp.tool
    async def set_diet_preferences(
        diet_preferences_markdown: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's saved diet-preferences markdown.

        Parameters:
            diet_preferences_markdown: New markdown content for diet
                preferences and recommendation hints.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation including `saved`, `subject`,
                and `bytes`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        result = await resolved_store.set_diet_preferences(
            identity.storage_subject(),
            diet_preferences_markdown,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def get_diet_goals(ctx: Context = CURRENT_CONTEXT) -> str:
        """Return the caller's saved diet-goals markdown.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored markdown, or an empty string when no goals have been
                saved yet.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_diet_goals(identity.storage_subject())

    @mcp.tool
    async def set_diet_goals(
        diet_goals_markdown: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's saved diet-goals markdown.

        Parameters:
            diet_goals_markdown: New markdown content for diet goals.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation including `saved`, `subject`,
                and `bytes`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        result = await resolved_store.set_diet_goals(
            identity.storage_subject(),
            diet_goals_markdown,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def get_training_goals(ctx: Context = CURRENT_CONTEXT) -> str:
        """Return the caller's saved training-goals markdown.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored markdown, or an empty string when no goals have been
                saved yet.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_training_goals(identity.storage_subject())

    @mcp.tool
    async def set_training_goals(
        training_goals_markdown: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Overwrite the caller's saved training-goals markdown.

        Parameters:
            training_goals_markdown: New markdown content for training goals.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Save confirmation including `saved`, `subject`,
                and `bytes`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        result = await resolved_store.set_training_goals(
            identity.storage_subject(),
            training_goals_markdown,
            login=identity.login,
        )
        return result.as_dict()

    @mcp.tool
    async def list_products(ctx: Context = CURRENT_CONTEXT) -> list[ProductRecord]:
        """List the caller's private food-product catalog.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Product rows ordered by name.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_products(identity.storage_subject())

    @mcp.tool
    async def get_product(
        product_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> ProductRecord | None:
        """Return one food product from the caller's private catalog.

        Parameters:
            product_id: Product identifier to fetch.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Product row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_product(
            identity.storage_subject(),
            product_id,
        )

    @mcp.tool
    async def add_product(
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> ProductRecord:
        """Add one food product to the caller's private catalog.

        Parameters:
            name: Product display name.
            default_serving_g: Optional common serving size in grams.
            calories_per_100g: Calories per 100 grams.
            carbs_g_per_100g: Carbohydrates per 100 grams.
            protein_g_per_100g: Protein per 100 grams.
            fat_g_per_100g: Fat per 100 grams.
            notes_markdown: Optional product notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Newly created product row.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.add_product(
            identity.storage_subject(),
            name=name,
            default_serving_g=default_serving_g,
            calories_per_100g=calories_per_100g,
            carbs_g_per_100g=carbs_g_per_100g,
            protein_g_per_100g=protein_g_per_100g,
            fat_g_per_100g=fat_g_per_100g,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def update_product(
        product_id: int,
        name: str,
        default_serving_g: float | None,
        calories_per_100g: float,
        carbs_g_per_100g: float,
        protein_g_per_100g: float,
        fat_g_per_100g: float,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> ProductRecord | None:
        """Replace one food product from the caller's private catalog.

        Parameters:
            product_id: Product identifier to update.
            name: Updated display name.
            default_serving_g: Updated optional serving size in grams.
            calories_per_100g: Updated calories per 100 grams.
            carbs_g_per_100g: Updated carbohydrates per 100 grams.
            protein_g_per_100g: Updated protein per 100 grams.
            fat_g_per_100g: Updated fat per 100 grams.
            notes_markdown: Updated product notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Updated product row, or `null` when
                missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.update_product(
            identity.storage_subject(),
            product_id=product_id,
            name=name,
            default_serving_g=default_serving_g,
            calories_per_100g=calories_per_100g,
            carbs_g_per_100g=carbs_g_per_100g,
            protein_g_per_100g=protein_g_per_100g,
            fat_g_per_100g=fat_g_per_100g,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def delete_product(
        product_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete one food product from the caller's private catalog.

        Parameters:
            product_id: Product identifier to delete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including a boolean flag.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_product(
            identity.storage_subject(),
            product_id,
        )

    @mcp.tool
    async def list_daily_targets(
        date_from: str | None = None,
        date_to: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> list[DailyTargetRecord]:
        """List the caller's daily targets, optionally within a date range.

        Parameters:
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Daily target rows ordered by date.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_daily_targets(
            identity.storage_subject(),
            date_from=date_from,
            date_to=date_to,
        )

    @mcp.tool
    async def get_daily_target(
        target_date: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> DailyTargetRecord | None:
        """Return the caller's daily target row for one calendar date.

        Parameters:
            target_date: ISO date string such as `2026-04-14`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Daily target row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_daily_target(
            identity.storage_subject(),
            target_date,
        )

    @mcp.tool
    async def set_daily_target(
        target_date: str,
        target_food_calories: float,
        target_exercise_calories: float,
        target_protein_g: float,
        target_carbs_g: float,
        target_fat_g: float,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> DailyTargetRecord:
        """Create or replace the caller's daily target row for one date.

        Parameters:
            target_date: ISO date string such as `2026-04-14`.
            target_food_calories: Target calories from food for the day.
            target_exercise_calories: Target calories expected from exercise.
            target_protein_g: Target grams of protein.
            target_carbs_g: Target grams of carbohydrates.
            target_fat_g: Target grams of fat.
            notes_markdown: Optional freeform notes for the day.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Upserted daily target row.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.set_daily_target(
            identity.storage_subject(),
            target_date=target_date,
            target_food_calories=target_food_calories,
            target_exercise_calories=target_exercise_calories,
            target_protein_g=target_protein_g,
            target_carbs_g=target_carbs_g,
            target_fat_g=target_fat_g,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def delete_daily_target(
        target_date: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete the caller's daily target row for one calendar date.

        Parameters:
            target_date: ISO date string such as `2026-04-14`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including the requested date.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_daily_target(
            identity.storage_subject(),
            target_date,
        )

    @mcp.tool
    async def list_daily_meals(
        meal_date: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> list[MealRecord]:
        """List the caller's meal headers, optionally scoped to one day.

        Parameters:
            meal_date: Optional ISO date string.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Meal-header rows ordered by date.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_daily_meals(
            identity.storage_subject(),
            meal_date=meal_date,
        )

    @mcp.tool
    async def get_meal(
        meal_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MealRecord | None:
        """Return one meal header owned by the current caller.

        Parameters:
            meal_id: Meal identifier to fetch.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Meal row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_meal(identity.storage_subject(), meal_id)

    @mcp.tool
    async def add_meal(
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> MealRecord:
        """Add one meal header for the current caller.

        Parameters:
            meal_date: ISO calendar date for the meal.
            meal_label: Free-text meal label such as `breakfast`.
            notes_markdown: Optional freeform notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Newly created meal row.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.add_meal(
            identity.storage_subject(),
            meal_date=meal_date,
            meal_label=meal_label,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def update_meal(
        meal_id: int,
        meal_date: str,
        meal_label: str,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> MealRecord | None:
        """Replace one meal header owned by the current caller.

        Parameters:
            meal_id: Meal identifier to update.
            meal_date: Replacement ISO calendar date.
            meal_label: Replacement free-text meal label.
            notes_markdown: Replacement freeform notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Updated meal row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.update_meal(
            identity.storage_subject(),
            meal_id=meal_id,
            meal_date=meal_date,
            meal_label=meal_label,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def delete_meal(
        meal_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete one meal header owned by the current caller.

        Parameters:
            meal_id: Meal identifier to delete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including a boolean flag.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_meal(identity.storage_subject(), meal_id)

    @mcp.tool
    async def list_meal_items(
        meal_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> list[MealItemRecord]:
        """List meal items attached to one caller-owned meal.

        Parameters:
            meal_id: Parent meal identifier.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Meal item rows ordered by id.

        Raises:
            RuntimeError: If authentication is required or the meal is invalid.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_meal_items(
            identity.storage_subject(),
            meal_id,
        )

    @mcp.tool
    async def add_meal_item(
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MealItemRecord:
        """Add one meal item for the current caller.

        Parameters:
            meal_id: Parent meal identifier.
            grams: Consumed grams for the item.
            ingredient_name: Optional free-text ingredient name.
            product_id: Optional catalog product identifier used for automatic
                nutrient scaling.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Newly created meal-item row.

        Raises:
            RuntimeError: If authentication is required or the meal/product is
                invalid.
            ValueError: If manual nutrient values are incomplete.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.add_meal_item(
            identity.storage_subject(),
            meal_id=meal_id,
            grams=grams,
            ingredient_name=ingredient_name,
            product_id=product_id,
            calories=calories,
            carbs_g=carbs_g,
            protein_g=protein_g,
            fat_g=fat_g,
        )

    @mcp.tool
    async def update_meal_item(
        meal_item_id: int,
        meal_id: int,
        grams: float,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MealItemRecord | None:
        """Replace one meal item owned by the current caller.

        Parameters:
            meal_item_id: Meal-item identifier to update.
            meal_id: Replacement parent meal identifier.
            grams: Replacement consumed grams.
            ingredient_name: Replacement free-text ingredient name.
            product_id: Replacement catalog product identifier, if any.
            calories: Replacement manual calories for non-catalog items.
            carbs_g: Replacement carbohydrate grams for non-catalog items.
            protein_g: Replacement protein grams for non-catalog items.
            fat_g: Replacement fat grams for non-catalog items.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Updated meal-item row, or `null` when
                missing.

        Raises:
            RuntimeError: If authentication is required or the meal/product is
                invalid.
            ValueError: If manual nutrient values are incomplete.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.update_meal_item(
            identity.storage_subject(),
            meal_item_id=meal_item_id,
            meal_id=meal_id,
            grams=grams,
            ingredient_name=ingredient_name,
            product_id=product_id,
            calories=calories,
            carbs_g=carbs_g,
            protein_g=protein_g,
            fat_g=fat_g,
        )

    @mcp.tool
    async def delete_meal_item(
        meal_item_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete one meal item owned by the current caller.

        Parameters:
            meal_item_id: Meal-item identifier to delete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including a boolean flag.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_meal_item(
            identity.storage_subject(),
            meal_item_id,
        )

    @mcp.tool
    async def list_activities(
        date_from: str | None = None,
        date_to: str | None = None,
        external_source: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> list[ActivityRecord]:
        """List activity entries owned by the current caller.

        Parameters:
            date_from: Optional inclusive lower ISO date bound.
            date_to: Optional inclusive upper ISO date bound.
            external_source: Optional filter such as `strava`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Activity rows ordered by date.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_activities(
            identity.storage_subject(),
            date_from=date_from,
            date_to=date_to,
            external_source=external_source,
        )

    @mcp.tool
    async def get_activity(
        activity_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> ActivityRecord | None:
        """Return one activity entry owned by the current caller.

        Parameters:
            activity_id: Activity identifier to fetch.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Activity row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_activity(
            identity.storage_subject(),
            activity_id,
        )

    @mcp.tool
    async def add_activity(
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
        zones: dict[str, Any] | None = None,
        laps: list[dict[str, Any]] | None = None,
        streams: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> ActivityRecord:
        """Add one activity entry for the current caller.

        Parameters:
            activity_date: ISO calendar date for the activity.
            title: Human-readable activity title.
            external_source: Optional external source such as `strava`.
            external_activity_id: Optional upstream activity identifier.
            athlete_id: Optional upstream athlete identifier.
            sport_type: Optional sport or activity type.
            distance_meters: Optional distance in meters.
            moving_time_seconds: Optional moving time in seconds.
            elapsed_time_seconds: Optional elapsed time in seconds.
            total_elevation_gain_meters: Optional elevation gain in meters.
            average_speed_mps: Optional average speed in meters per second.
            max_speed_mps: Optional max speed in meters per second.
            average_heartrate: Optional average heart rate.
            max_heartrate: Optional max heart rate.
            average_watts: Optional average power.
            weighted_average_watts: Optional weighted average power.
            calories: Optional exercise calories.
            kilojoules: Optional work in kilojoules.
            suffer_score: Optional training-stress score.
            trainer: Whether the activity happened on a trainer.
            commute: Whether the activity was a commute.
            manual: Whether the row was manually created.
            is_private: Whether the source marks the activity as private.
            zones: Optional zone summary JSON.
            laps: Optional lap JSON list.
            streams: Optional stream JSON object.
            raw_payload: Optional raw provider payload JSON.
            notes_markdown: Optional freeform notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Newly created activity row.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.add_activity(
            identity.storage_subject(),
            activity_date=activity_date,
            title=title,
            external_source=external_source,
            external_activity_id=external_activity_id,
            athlete_id=athlete_id,
            sport_type=sport_type,
            distance_meters=distance_meters,
            moving_time_seconds=moving_time_seconds,
            elapsed_time_seconds=elapsed_time_seconds,
            total_elevation_gain_meters=total_elevation_gain_meters,
            average_speed_mps=average_speed_mps,
            max_speed_mps=max_speed_mps,
            average_heartrate=average_heartrate,
            max_heartrate=max_heartrate,
            average_watts=average_watts,
            weighted_average_watts=weighted_average_watts,
            calories=calories,
            kilojoules=kilojoules,
            suffer_score=suffer_score,
            trainer=trainer,
            commute=commute,
            manual=manual,
            is_private=is_private,
            zones=zones,
            laps=laps,
            streams=streams,
            raw_payload=raw_payload,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def update_activity(
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
        zones: dict[str, Any] | None = None,
        laps: list[dict[str, Any]] | None = None,
        streams: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> ActivityRecord | None:
        """Replace one activity entry owned by the current caller.

        Parameters:
            activity_id: Activity identifier to update.
            activity_date: Replacement ISO calendar date.
            title: Replacement activity title.
            external_source: Replacement external source.
            external_activity_id: Replacement upstream activity identifier.
            athlete_id: Replacement upstream athlete identifier.
            sport_type: Replacement sport type.
            distance_meters: Replacement distance in meters.
            moving_time_seconds: Replacement moving time in seconds.
            elapsed_time_seconds: Replacement elapsed time in seconds.
            total_elevation_gain_meters: Replacement elevation gain in meters.
            average_speed_mps: Replacement average speed in meters per second.
            max_speed_mps: Replacement max speed in meters per second.
            average_heartrate: Replacement average heart rate.
            max_heartrate: Replacement max heart rate.
            average_watts: Replacement average power.
            weighted_average_watts: Replacement weighted average power.
            calories: Replacement exercise calories.
            kilojoules: Replacement work in kilojoules.
            suffer_score: Replacement training-stress score.
            trainer: Replacement trainer flag.
            commute: Replacement commute flag.
            manual: Replacement manual flag.
            is_private: Replacement privacy flag.
            zones: Replacement zone summary JSON.
            laps: Replacement lap JSON list.
            streams: Replacement stream JSON object.
            raw_payload: Replacement raw provider payload JSON.
            notes_markdown: Replacement freeform notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Updated activity row, or `null` when
                missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.update_activity(
            identity.storage_subject(),
            activity_id=activity_id,
            activity_date=activity_date,
            title=title,
            external_source=external_source,
            external_activity_id=external_activity_id,
            athlete_id=athlete_id,
            sport_type=sport_type,
            distance_meters=distance_meters,
            moving_time_seconds=moving_time_seconds,
            elapsed_time_seconds=elapsed_time_seconds,
            total_elevation_gain_meters=total_elevation_gain_meters,
            average_speed_mps=average_speed_mps,
            max_speed_mps=max_speed_mps,
            average_heartrate=average_heartrate,
            max_heartrate=max_heartrate,
            average_watts=average_watts,
            weighted_average_watts=weighted_average_watts,
            calories=calories,
            kilojoules=kilojoules,
            suffer_score=suffer_score,
            trainer=trainer,
            commute=commute,
            manual=manual,
            is_private=is_private,
            zones=zones,
            laps=laps,
            streams=streams,
            raw_payload=raw_payload,
            notes_markdown=notes_markdown,
        )

    @mcp.tool
    async def delete_activity(
        activity_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete one activity entry owned by the current caller.

        Parameters:
            activity_id: Activity identifier to delete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including a boolean flag.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_activity(
            identity.storage_subject(),
            activity_id,
        )

    @mcp.tool
    async def list_memory_items(
        category: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> list[MemoryItemRecord]:
        """List long-term memory items owned by the current caller.

        Parameters:
            category: Optional category filter.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            list[dict[str, object]]: Memory-item rows ordered by recency.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.list_memory_items(
            identity.storage_subject(),
            category=category,
        )

    @mcp.tool
    async def get_memory_item(
        memory_item_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MemoryItemRecord | None:
        """Return one long-term memory item owned by the current caller.

        Parameters:
            memory_item_id: Memory-item identifier to fetch.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Memory row, or `null` when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_memory_item(
            identity.storage_subject(),
            memory_item_id,
        )

    @mcp.tool
    async def add_memory_item(
        title: str,
        content_markdown: str,
        category: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MemoryItemRecord:
        """Add one long-term memory item for the current caller.

        Parameters:
            title: Short memory title.
            content_markdown: Main markdown content to remember.
            category: Optional category or tag.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Newly created memory row.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.add_memory_item(
            identity.storage_subject(),
            title=title,
            content_markdown=content_markdown,
            category=category,
        )

    @mcp.tool
    async def update_memory_item(
        memory_item_id: int,
        title: str,
        content_markdown: str,
        category: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> MemoryItemRecord | None:
        """Replace one long-term memory item owned by the current caller.

        Parameters:
            memory_item_id: Memory-item identifier to update.
            title: Replacement memory title.
            content_markdown: Replacement markdown content.
            category: Replacement category or tag.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object] | None: Updated memory row, or `null` when
                missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.update_memory_item(
            identity.storage_subject(),
            memory_item_id=memory_item_id,
            title=title,
            content_markdown=content_markdown,
            category=category,
        )

    @mcp.tool
    async def delete_memory_item(
        memory_item_id: int,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Delete one long-term memory item owned by the current caller.

        Parameters:
            memory_item_id: Memory-item identifier to delete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Deletion result including a boolean flag.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.delete_memory_item(
            identity.storage_subject(),
            memory_item_id,
        )

    @mcp.tool
    async def get_daily_summary(
        target_date: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> DailySummaryRecord:
        """Return the caller's computed target-vs-actual summary for one day.

        Parameters:
            target_date: ISO date string such as `2026-04-14`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Combined targets, actual totals, and counts.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        # Actuals are computed on read so logs remain the source of truth and
        # we avoid a second table that could drift out of sync.
        return await resolved_store.get_daily_summary(
            identity.storage_subject(),
            target_date,
        )

    @mcp.tool
    async def whoami(ctx: Context = CURRENT_CONTEXT) -> dict[str, object]:
        """Return the current caller identity for auth debugging.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Diagnostic identity payload with `authenticated`,
                `subject`, `login`, and `request_id`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
        """

        identity = current_identity(ctx)
        return identity.as_whoami_response()

    @mcp.resource(
        "profile://me",
        mime_type="text/markdown",
        annotations={"readOnlyHint": True, "idempotentHint": True},
        description="The current caller's saved profile markdown.",
    )
    async def profile_resource(ctx: Context = CURRENT_CONTEXT) -> str:
        """Expose the current caller's profile as a readable MCP resource.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored profile markdown, or an empty string when missing.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_profile(identity.storage_subject())

    @mcp.prompt(
        description="Inject the caller's saved profile into a simple task prompt.",
    )
    async def use_profile(task: str, ctx: Context = CURRENT_CONTEXT) -> PromptResult:
        """Generate a prompt that includes the caller's saved profile.

        Parameters:
            task: Task the downstream LLM should complete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            PromptResult: A single-message prompt enriched with the caller's
                stored profile markdown.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        profile_markdown = await resolved_store.get_profile(identity.storage_subject())

        if profile_markdown.strip():
            profile_block = profile_markdown
            has_profile = True
        else:
            profile_block = "No profile is saved yet for this caller."
            has_profile = False

        return PromptResult(
            messages=[
                Message(
                    "Use the following persona profile while completing the "
                    "task.\n\n"
                    f"Task:\n{task}\n\n"
                    f"Profile:\n{profile_block}"
                )
            ],
            description="Prompt enriched with the caller's saved profile.",
            meta={"has_profile": has_profile},
        )

    return mcp
