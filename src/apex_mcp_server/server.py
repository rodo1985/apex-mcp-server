"""FastMCP server assembly for the wellness pilot."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp import Context, FastMCP
from fastmcp.dependencies import CurrentContext
from fastmcp.prompts import Message, PromptResult

from apex_mcp_server.auth import build_auth_provider
from apex_mcp_server.config import Settings
from apex_mcp_server.identity import resolve_identity
from apex_mcp_server.models import DailySummaryRecord, UserData, UserIdentity
from apex_mcp_server.storage import UserStore, build_user_store

CURRENT_CONTEXT = CurrentContext()
DocumentName = Literal["profile", "diet_preferences", "diet_goals", "training_goals"]
DocumentOperation = Literal["get", "set"]
UserDataOperation = Literal["get", "set"]
ProductOperation = Literal["list", "get", "add", "update", "delete"]
DailyTargetOperation = Literal["list", "get", "set", "delete"]
MealOperation = Literal["list", "get", "add", "update", "delete"]
MealItemOperation = Literal["list", "add", "update", "delete"]
ActivityOperation = Literal["list", "get", "add", "update", "delete"]
MemoryOperation = Literal["list", "get", "add", "update", "delete"]


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
            "APEX is an AI personal trainer and dietitian for endurance "
            "athletes. This MCP server stores the caller's persistent "
            "wellness context so an agent can reason over user "
            "profile documents, body metrics, nutrition preferences, daily "
            "targets, meal logs, training activities, and long-term memory. "
            "Use the grouped domain tools to read and update stable user "
            "documents, body metrics, food products, daily targets, meal "
            "logs, training history, and long-term memory. Use "
            "get_daily_summary when you need one computed view of targets "
            "versus actual intake and exercise for a given date."
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

    def _require_value(
        value: object | None,
        name: str,
        operation: str,
    ) -> object:
        """Require an operation-specific parameter and fail clearly when missing.

        Parameters:
            value: Raw parameter value provided by the caller.
            name: Human-readable parameter name used in the error message.
            operation: Operation currently being performed.

        Returns:
            object: The provided value when it is not `None`.

        Raises:
            ValueError: If the value is missing.
        """

        if value is None:
            raise ValueError(f"{name} is required when operation='{operation}'.")
        return value

    def _item_result(
        operation: str,
        item: dict[str, object] | None,
    ) -> dict[str, object]:
        """Wrap one item-style response with the executed operation.

        Parameters:
            operation: Operation performed by the grouped tool.
            item: Returned row payload, or `None` when missing.

        Returns:
            dict[str, object]: Normalized item response.
        """

        return {"operation": operation, "item": item}

    def _items_result(
        operation: str,
        items: list[dict[str, object]],
    ) -> dict[str, object]:
        """Wrap a list-style response with item count metadata.

        Parameters:
            operation: Operation performed by the grouped tool.
            items: Returned row payloads.

        Returns:
            dict[str, object]: Normalized list response.
        """

        return {"operation": operation, "count": len(items), "items": items}

    def _document_methods(document: DocumentName) -> tuple[str, str]:
        """Return the store getter and setter names for one singleton document.

        Parameters:
            document: Requested singleton document name.

        Returns:
            tuple[str, str]: Getter and setter method names on `UserStore`.
        """

        mapping = {
            "profile": ("get_profile", "set_profile"),
            "diet_preferences": (
                "get_diet_preferences",
                "set_diet_preferences",
            ),
            "diet_goals": ("get_diet_goals", "set_diet_goals"),
            "training_goals": ("get_training_goals", "set_training_goals"),
        }
        return mapping[document]

    @mcp.tool
    async def profile_documents(
        operation: DocumentOperation,
        document: DocumentName,
        markdown: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Read or update one singleton APEX markdown document.

        Parameters:
            operation: Either `get` or `set`.
            document: Singleton document name: `profile`,
                `diet_preferences`, `diet_goals`, or `training_goals`.
            markdown: Replacement markdown content required for `set`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: For `get`, returns `document` plus `markdown`.
                For `set`, returns the save confirmation with `document` and
                `operation` added. These documents hold the athlete's broad
                profile, nutrition preferences, diet goals, and training goals.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        getter_name, setter_name = _document_methods(document)
        subject = identity.storage_subject()

        if operation == "get":
            markdown_value = await getattr(resolved_store, getter_name)(subject)
            return {
                "operation": operation,
                "document": document,
                "markdown": markdown_value,
            }

        markdown_value = str(_require_value(markdown, "markdown", operation))
        result = await getattr(resolved_store, setter_name)(
            subject,
            markdown_value,
            login=identity.login,
        )
        payload = result.as_dict()
        payload["operation"] = operation
        payload["document"] = document
        return payload

    @mcp.tool
    async def user_data(
        operation: UserDataOperation,
        weight_kg: float | None = None,
        height_cm: float | None = None,
        ftp_watts: int | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Read or update the caller's numeric body and performance metrics.

        Parameters:
            operation: Either `get` or `set`.
            weight_kg: Body weight in kilograms used for `set`.
            height_cm: Height in centimeters used for `set`.
            ftp_watts: Cycling FTP in watts used for `set`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Numeric fields for `get`, or the save
                confirmation plus stored values for `set`.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "get":
            data = await resolved_store.get_user_data(subject)
            payload = data.as_dict()
            payload["operation"] = operation
            return payload

        data = UserData(
            weight_kg=weight_kg,
            height_cm=height_cm,
            ftp_watts=ftp_watts,
        )
        result = await resolved_store.set_user_data(
            subject,
            data,
            login=identity.login,
        )
        payload = result.as_dict()
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def products(
        operation: ProductOperation,
        product_id: int | None = None,
        name: str | None = None,
        default_serving_g: float | None = None,
        calories_per_100g: float | None = None,
        carbs_g_per_100g: float | None = None,
        protein_g_per_100g: float | None = None,
        fat_g_per_100g: float | None = None,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Manage reusable food products in the caller's private catalog.

        Parameters:
            operation: One of `list`, `get`, `add`, `update`, or `delete`.
            product_id: Product identifier required for `get`, `update`, and
                `delete`.
            name: Product display name required for `add` and `update`.
            default_serving_g: Optional common serving size in grams.
            calories_per_100g: Calories per 100 grams for `add` and `update`.
            carbs_g_per_100g: Carbs per 100 grams for `add` and `update`.
            protein_g_per_100g: Protein per 100 grams for `add` and `update`.
            fat_g_per_100g: Fat per 100 grams for `add` and `update`.
            notes_markdown: Optional product notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; get/add/update
                return `item`; delete returns deletion metadata. Products are
                reusable food entries that support quicker meal logging later.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(operation, await resolved_store.list_products(subject))
        if operation == "get":
            return _item_result(
                operation,
                await resolved_store.get_product(
                    subject,
                    int(_require_value(product_id, "product_id", operation)),
                ),
            )
        if operation == "add":
            return _item_result(
                operation,
                await resolved_store.add_product(
                    subject,
                    name=str(_require_value(name, "name", operation)),
                    default_serving_g=default_serving_g,
                    calories_per_100g=float(
                        _require_value(
                            calories_per_100g,
                            "calories_per_100g",
                            operation,
                        )
                    ),
                    carbs_g_per_100g=float(
                        _require_value(carbs_g_per_100g, "carbs_g_per_100g", operation)
                    ),
                    protein_g_per_100g=float(
                        _require_value(
                            protein_g_per_100g,
                            "protein_g_per_100g",
                            operation,
                        )
                    ),
                    fat_g_per_100g=float(
                        _require_value(fat_g_per_100g, "fat_g_per_100g", operation)
                    ),
                    notes_markdown=notes_markdown,
                ),
            )
        if operation == "update":
            return _item_result(
                operation,
                await resolved_store.update_product(
                    subject,
                    product_id=int(_require_value(product_id, "product_id", operation)),
                    name=str(_require_value(name, "name", operation)),
                    default_serving_g=default_serving_g,
                    calories_per_100g=float(
                        _require_value(
                            calories_per_100g,
                            "calories_per_100g",
                            operation,
                        )
                    ),
                    carbs_g_per_100g=float(
                        _require_value(carbs_g_per_100g, "carbs_g_per_100g", operation)
                    ),
                    protein_g_per_100g=float(
                        _require_value(
                            protein_g_per_100g,
                            "protein_g_per_100g",
                            operation,
                        )
                    ),
                    fat_g_per_100g=float(
                        _require_value(fat_g_per_100g, "fat_g_per_100g", operation)
                    ),
                    notes_markdown=notes_markdown,
                ),
            )

        payload = await resolved_store.delete_product(
            subject,
            int(_require_value(product_id, "product_id", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def daily_targets(
        operation: DailyTargetOperation,
        target_date: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        target_food_calories: float | None = None,
        target_exercise_calories: float | None = None,
        target_protein_g: float | None = None,
        target_carbs_g: float | None = None,
        target_fat_g: float | None = None,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Manage the caller's per-day nutrition and exercise targets.

        Parameters:
            operation: One of `list`, `get`, `set`, or `delete`.
            target_date: Target ISO date required for `get`, `set`, and
                `delete`.
            date_from: Optional lower ISO date bound for `list`.
            date_to: Optional upper ISO date bound for `list`.
            target_food_calories: Planned food calories for `set`.
            target_exercise_calories: Planned exercise calories for `set`.
            target_protein_g: Planned protein grams for `set`.
            target_carbs_g: Planned carbohydrate grams for `set`.
            target_fat_g: Planned fat grams for `set`.
            notes_markdown: Optional planning notes for `set`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; get/set return
                `item`; delete returns deletion metadata.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(
                operation,
                await resolved_store.list_daily_targets(
                    subject,
                    date_from=date_from,
                    date_to=date_to,
                ),
            )
        if operation == "get":
            return _item_result(
                operation,
                await resolved_store.get_daily_target(
                    subject,
                    str(_require_value(target_date, "target_date", operation)),
                ),
            )
        if operation == "set":
            return _item_result(
                operation,
                await resolved_store.set_daily_target(
                    subject,
                    target_date=str(
                        _require_value(target_date, "target_date", operation)
                    ),
                    target_food_calories=float(
                        _require_value(
                            target_food_calories,
                            "target_food_calories",
                            operation,
                        )
                    ),
                    target_exercise_calories=float(
                        _require_value(
                            target_exercise_calories,
                            "target_exercise_calories",
                            operation,
                        )
                    ),
                    target_protein_g=float(
                        _require_value(target_protein_g, "target_protein_g", operation)
                    ),
                    target_carbs_g=float(
                        _require_value(target_carbs_g, "target_carbs_g", operation)
                    ),
                    target_fat_g=float(
                        _require_value(target_fat_g, "target_fat_g", operation)
                    ),
                    notes_markdown=notes_markdown,
                ),
            )

        payload = await resolved_store.delete_daily_target(
            subject,
            str(_require_value(target_date, "target_date", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def meals(
        operation: MealOperation,
        meal_id: int | None = None,
        meal_date: str | None = None,
        meal_label: str | None = None,
        notes_markdown: str = "",
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Manage caller-owned meal headers for one or more calendar days.

        Parameters:
            operation: One of `list`, `get`, `add`, `update`, or `delete`.
            meal_id: Meal identifier required for `get`, `update`, and
                `delete`.
            meal_date: Meal ISO date used for `list`, `add`, and `update`.
            meal_label: User-defined meal label required for `add` and
                `update`.
            notes_markdown: Optional freeform meal notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; get/add/update
                return `item`; delete returns deletion metadata.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(
                operation,
                await resolved_store.list_daily_meals(subject, meal_date=meal_date),
            )
        if operation == "get":
            return _item_result(
                operation,
                await resolved_store.get_meal(
                    subject,
                    int(_require_value(meal_id, "meal_id", operation)),
                ),
            )
        if operation == "add":
            return _item_result(
                operation,
                await resolved_store.add_meal(
                    subject,
                    meal_date=str(_require_value(meal_date, "meal_date", operation)),
                    meal_label=str(_require_value(meal_label, "meal_label", operation)),
                    notes_markdown=notes_markdown,
                ),
            )
        if operation == "update":
            return _item_result(
                operation,
                await resolved_store.update_meal(
                    subject,
                    meal_id=int(_require_value(meal_id, "meal_id", operation)),
                    meal_date=str(_require_value(meal_date, "meal_date", operation)),
                    meal_label=str(_require_value(meal_label, "meal_label", operation)),
                    notes_markdown=notes_markdown,
                ),
            )

        payload = await resolved_store.delete_meal(
            subject,
            int(_require_value(meal_id, "meal_id", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def meal_items(
        operation: MealItemOperation,
        meal_id: int | None = None,
        meal_item_id: int | None = None,
        grams: float | None = None,
        ingredient_name: str | None = None,
        product_id: int | None = None,
        calories: float | None = None,
        carbs_g: float | None = None,
        protein_g: float | None = None,
        fat_g: float | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Manage the food items inside one caller-owned meal.

        Parameters:
            operation: One of `list`, `add`, `update`, or `delete`.
            meal_id: Parent meal identifier required for `list`, `add`, and
                `update`.
            meal_item_id: Meal-item identifier required for `update` and
                `delete`.
            grams: Consumed grams required for `add` and `update`.
            ingredient_name: Optional free-text ingredient name.
            product_id: Optional catalog product identifier.
            calories: Manual calories for non-catalog items.
            carbs_g: Manual carbohydrate grams for non-catalog items.
            protein_g: Manual protein grams for non-catalog items.
            fat_g: Manual fat grams for non-catalog items.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; add/update
                return `item`; delete returns deletion metadata.

        Raises:
            RuntimeError: If authentication is required or the meal/product is
                invalid.
            ValueError: If the requested operation is missing required fields
                or manual nutrient values are incomplete.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(
                operation,
                await resolved_store.list_meal_items(
                    subject,
                    meal_id=int(_require_value(meal_id, "meal_id", operation)),
                ),
            )
        if operation == "add":
            return _item_result(
                operation,
                await resolved_store.add_meal_item(
                    subject,
                    meal_id=int(_require_value(meal_id, "meal_id", operation)),
                    grams=float(_require_value(grams, "grams", operation)),
                    ingredient_name=ingredient_name,
                    product_id=product_id,
                    calories=calories,
                    carbs_g=carbs_g,
                    protein_g=protein_g,
                    fat_g=fat_g,
                ),
            )
        if operation == "update":
            return _item_result(
                operation,
                await resolved_store.update_meal_item(
                    subject,
                    meal_item_id=int(
                        _require_value(meal_item_id, "meal_item_id", operation)
                    ),
                    meal_id=int(_require_value(meal_id, "meal_id", operation)),
                    grams=float(_require_value(grams, "grams", operation)),
                    ingredient_name=ingredient_name,
                    product_id=product_id,
                    calories=calories,
                    carbs_g=carbs_g,
                    protein_g=protein_g,
                    fat_g=fat_g,
                ),
            )

        payload = await resolved_store.delete_meal_item(
            subject,
            int(_require_value(meal_item_id, "meal_item_id", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def activities(
        operation: ActivityOperation,
        activity_id: int | None = None,
        activity_date: str | None = None,
        title: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
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
    ) -> dict[str, object]:
        """Manage the caller's training-activity history.

        Parameters:
            operation: One of `list`, `get`, `add`, `update`, or `delete`.
            activity_id: Activity identifier required for `get`, `update`, and
                `delete`.
            activity_date: Activity ISO date required for `add` and `update`.
            title: Human-readable title required for `add` and `update`.
            date_from: Optional lower ISO date bound for `list`.
            date_to: Optional upper ISO date bound for `list`.
            external_source: Optional sync source such as `strava`.
            external_activity_id: Optional upstream activity identifier.
            athlete_id: Optional upstream athlete identifier.
            sport_type: Optional sport or activity type.
            distance_meters: Optional distance in meters.
            moving_time_seconds: Optional moving time in seconds.
            elapsed_time_seconds: Optional elapsed time in seconds.
            total_elevation_gain_meters: Optional elevation gain in meters.
            average_speed_mps: Optional average speed in m/s.
            max_speed_mps: Optional max speed in m/s.
            average_heartrate: Optional average heart rate.
            max_heartrate: Optional max heart rate.
            average_watts: Optional average power.
            weighted_average_watts: Optional weighted average power.
            calories: Optional exercise calories burned.
            kilojoules: Optional work in kilojoules.
            suffer_score: Optional training-load metric.
            trainer: Whether the activity happened on a trainer.
            commute: Whether the activity was a commute.
            manual: Whether the row was entered manually.
            is_private: Whether the activity is private upstream.
            zones: Optional zones JSON summary.
            laps: Optional laps JSON list.
            streams: Optional streams JSON object.
            raw_payload: Optional raw provider payload JSON.
            notes_markdown: Optional freeform notes.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; get/add/update
                return `item`; delete returns deletion metadata.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(
                operation,
                await resolved_store.list_activities(
                    subject,
                    date_from=date_from,
                    date_to=date_to,
                    external_source=external_source,
                ),
            )
        if operation == "get":
            return _item_result(
                operation,
                await resolved_store.get_activity(
                    subject,
                    int(_require_value(activity_id, "activity_id", operation)),
                ),
            )
        if operation == "add":
            return _item_result(
                operation,
                await resolved_store.add_activity(
                    subject,
                    activity_date=str(
                        _require_value(activity_date, "activity_date", operation)
                    ),
                    title=str(_require_value(title, "title", operation)),
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
                ),
            )
        if operation == "update":
            return _item_result(
                operation,
                await resolved_store.update_activity(
                    subject,
                    activity_id=int(
                        _require_value(activity_id, "activity_id", operation)
                    ),
                    activity_date=str(
                        _require_value(activity_date, "activity_date", operation)
                    ),
                    title=str(_require_value(title, "title", operation)),
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
                ),
            )

        payload = await resolved_store.delete_activity(
            subject,
            int(_require_value(activity_id, "activity_id", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def memory_items(
        operation: MemoryOperation,
        memory_item_id: int | None = None,
        title: str | None = None,
        content_markdown: str | None = None,
        category: str | None = None,
        ctx: Context = CURRENT_CONTEXT,
    ) -> dict[str, object]:
        """Manage the caller's long-term memory items.

        Parameters:
            operation: One of `list`, `get`, `add`, `update`, or `delete`.
            memory_item_id: Memory identifier required for `get`, `update`,
                and `delete`.
            title: Memory title required for `add` and `update`.
            content_markdown: Memory body required for `add` and `update`.
            category: Optional category filter or saved tag.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: List operations return `items`; get/add/update
                return `item`; delete returns deletion metadata.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            ValueError: If the requested operation is missing required fields.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        subject = identity.storage_subject()

        if operation == "list":
            return _items_result(
                operation,
                await resolved_store.list_memory_items(subject, category=category),
            )
        if operation == "get":
            return _item_result(
                operation,
                await resolved_store.get_memory_item(
                    subject,
                    int(_require_value(memory_item_id, "memory_item_id", operation)),
                ),
            )
        if operation == "add":
            return _item_result(
                operation,
                await resolved_store.add_memory_item(
                    subject,
                    title=str(_require_value(title, "title", operation)),
                    content_markdown=str(
                        _require_value(
                            content_markdown,
                            "content_markdown",
                            operation,
                        )
                    ),
                    category=category,
                ),
            )
        if operation == "update":
            return _item_result(
                operation,
                await resolved_store.update_memory_item(
                    subject,
                    memory_item_id=int(
                        _require_value(memory_item_id, "memory_item_id", operation)
                    ),
                    title=str(_require_value(title, "title", operation)),
                    content_markdown=str(
                        _require_value(
                            content_markdown,
                            "content_markdown",
                            operation,
                        )
                    ),
                    category=category,
                ),
            )

        payload = await resolved_store.delete_memory_item(
            subject,
            int(_require_value(memory_item_id, "memory_item_id", operation)),
        )
        payload["operation"] = operation
        return payload

    @mcp.tool
    async def get_daily_summary(
        target_date: str,
        ctx: Context = CURRENT_CONTEXT,
    ) -> DailySummaryRecord:
        """Return the caller's computed daily dashboard summary for one day.

        Parameters:
            target_date: ISO date string such as `2026-04-14`.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Combined targets, actual totals, and counts for
                one calendar day. This is the best single tool to answer
                questions like "how did today go?" because it merges planned
                targets, logged food intake, logged exercise calories, macro
                totals, and object counts across meals and activities.

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
        """Return the current caller identity and auth-scoping payload.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            dict[str, object]: Diagnostic identity payload with `authenticated`,
                `subject`, `login`, and `request_id`. This is mainly useful for
                debugging auth, confirming OAuth identity mapping, and checking
                which logical user namespace the current tools will read/write.

        Raises:
            RuntimeError: If authentication is required but unavailable.
        """

        identity = current_identity(ctx)
        return identity.as_whoami_response()

    @mcp.resource(
        "profile://me",
        mime_type="text/markdown",
        annotations={"readOnlyHint": True, "idempotentHint": True},
        description=(
            "The current caller's main APEX profile document as a readable "
            "markdown resource."
        ),
    )
    async def profile_resource(ctx: Context = CURRENT_CONTEXT) -> str:
        """Expose the current caller's main profile as a readable MCP resource.

        Parameters:
            ctx: Current FastMCP request context injected automatically.

        Returns:
            str: Stored profile markdown, or an empty string when missing. This
                resource is the read-only equivalent of
                `profile_documents(operation="get", document="profile")` and
                is useful when a client prefers resource access over tool
                calls.

        Raises:
            RuntimeError: If authentication is required but unavailable.
            Exception: Propagated from the configured storage backend.
        """

        identity = current_identity(ctx)
        return await resolved_store.get_profile(identity.storage_subject())

    @mcp.prompt(
        description=(
            "Inject the caller's saved APEX profile into a simple task prompt."
        ),
    )
    async def use_profile(task: str, ctx: Context = CURRENT_CONTEXT) -> PromptResult:
        """Generate a prompt that includes the caller's saved main profile.

        Parameters:
            task: Task the downstream LLM should complete.
            ctx: Current FastMCP request context injected automatically.

        Returns:
            PromptResult: A single-message prompt enriched with the caller's
                stored profile markdown. This is a convenience prompt for
                profile-aware downstream reasoning when an agent needs broad
                personal context but does not want to manually fetch and stitch
                the profile first.

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
