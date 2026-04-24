"""Small shared models for the Postgres-backed MCP pilot."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict


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


class ProductRecord(TypedDict):
    """Describe one food product row returned by the MCP server.

    Parameters:
        id: Product identifier.
        subject: Subject that owns the row.
        name: Product display name.
        default_serving_g: Optional default serving size in grams.
        calories_per_100g: Calories per 100 grams.
        carbs_g_per_100g: Carbohydrates per 100 grams.
        protein_g_per_100g: Protein per 100 grams.
        fat_g_per_100g: Fat per 100 grams.
        usage_count: Internal lifetime count of successful product-backed meal
            item additions.
        notes_markdown: Freeform markdown notes.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    name: str
    default_serving_g: float | None
    calories_per_100g: float
    carbs_g_per_100g: float
    protein_g_per_100g: float
    fat_g_per_100g: float
    usage_count: int
    notes_markdown: str
    created_at: str
    updated_at: str


class DailyTargetRecord(TypedDict):
    """Describe one daily target row returned by the MCP server.

    Parameters:
        id: Target identifier.
        subject: Subject that owns the row.
        target_date: Local business date in ISO format.
        target_food_calories: Planned calories from food.
        target_exercise_calories: Planned calories from exercise.
        target_protein_g: Planned protein grams.
        target_carbs_g: Planned carbohydrate grams.
        target_fat_g: Planned fat grams.
        notes_markdown: Freeform markdown notes.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    target_date: str
    target_food_calories: float
    target_exercise_calories: float
    target_protein_g: float
    target_carbs_g: float
    target_fat_g: float
    notes_markdown: str
    created_at: str
    updated_at: str


class DailyMetricRecord(TypedDict):
    """Describe one date-scoped wellness metric row returned by the MCP server.

    Parameters:
        id: Metric row identifier.
        subject: Subject that owns the row.
        metric_date: Local business date in ISO format.
        metric_type: Supported metric type such as `weight`.
        value: Numeric metric value.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    metric_date: str
    metric_type: str
    value: float
    created_at: str
    updated_at: str


class MealRecord(TypedDict):
    """Describe one meal header row returned by the MCP server.

    Parameters:
        id: Meal identifier.
        subject: Subject that owns the row.
        meal_date: Local business date in ISO format.
        meal_label: Free-text meal label.
        notes_markdown: Freeform markdown notes.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    meal_date: str
    meal_label: str
    notes_markdown: str
    created_at: str
    updated_at: str


class MealItemRecord(TypedDict):
    """Describe one meal-item row returned by the MCP server.

    Parameters:
        id: Meal-item identifier.
        subject: Subject that owns the row.
        meal_id: Parent meal identifier.
        product_id: Optional product identifier used for snapshotting.
        ingredient_name: Stored ingredient label.
        grams: Consumed grams.
        calories: Stored calorie snapshot.
        carbs_g: Stored carbohydrate snapshot.
        protein_g: Stored protein snapshot.
        fat_g: Stored fat snapshot.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    meal_id: int
    product_id: int | None
    ingredient_name: str
    grams: float
    calories: float
    carbs_g: float
    protein_g: float
    fat_g: float
    created_at: str
    updated_at: str


class ActivityRecord(TypedDict):
    """Describe one activity row returned by the MCP server.

    Parameters:
        id: Activity identifier.
        subject: Subject that owns the row.
        activity_date: Local business date in ISO format.
        title: Activity title.
        external_source: Optional upstream source such as `strava`.
        external_activity_id: Optional upstream activity id.
        athlete_id: Optional upstream athlete id.
        sport_type: Optional sport type.
        distance_meters: Optional distance in meters.
        moving_time_seconds: Optional moving time in seconds.
        elapsed_time_seconds: Optional elapsed time in seconds.
        total_elevation_gain_meters: Optional elevation gain in meters.
        average_speed_mps: Optional average speed in meters per second.
        max_speed_mps: Optional max speed in meters per second.
        average_heartrate: Optional average heart rate.
        max_heartrate: Optional max heart rate.
        average_watts: Optional average watts.
        weighted_average_watts: Optional weighted average watts.
        calories: Optional exercise calories.
        kilojoules: Optional work in kilojoules.
        suffer_score: Optional training-stress score.
        trainer: Trainer flag.
        commute: Commute flag.
        manual: Manual-entry flag.
        is_private: Privacy flag.
        zones: Optional JSON zone summary.
        laps: Optional JSON lap list.
        streams: Optional JSON stream payload.
        raw_payload: Optional raw provider payload.
        notes_markdown: Freeform markdown notes.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    activity_date: str
    title: str
    external_source: str | None
    external_activity_id: str | None
    athlete_id: str | None
    sport_type: str | None
    distance_meters: float | None
    moving_time_seconds: int | None
    elapsed_time_seconds: int | None
    total_elevation_gain_meters: float | None
    average_speed_mps: float | None
    max_speed_mps: float | None
    average_heartrate: float | None
    max_heartrate: float | None
    average_watts: float | None
    weighted_average_watts: float | None
    calories: float | None
    kilojoules: float | None
    suffer_score: float | None
    trainer: bool
    commute: bool
    manual: bool
    is_private: bool
    zones: Any
    laps: Any
    streams: Any
    raw_payload: Any
    notes_markdown: str
    created_at: str
    updated_at: str


class MemoryItemRecord(TypedDict):
    """Describe one long-term memory row returned by the MCP server.

    Parameters:
        id: Memory-item identifier.
        subject: Subject that owns the row.
        title: Memory title.
        category: Optional category or tag.
        content_markdown: Markdown content to remember.
        created_at: Creation timestamp in ISO format.
        updated_at: Update timestamp in ISO format.
    """

    id: int
    subject: str
    title: str
    category: str | None
    content_markdown: str
    created_at: str
    updated_at: str


class DailySummaryRecord(TypedDict):
    """Describe one computed target-vs-actual summary row.

    Parameters:
        target_date: Local business date in ISO format.
        target_food_calories: Optional planned calories from food.
        target_exercise_calories: Optional planned calories from exercise.
        target_protein_g: Optional planned protein grams.
        target_carbs_g: Optional planned carbohydrate grams.
        target_fat_g: Optional planned fat grams.
        actual_food_calories: Computed calories logged from meals.
        actual_exercise_calories: Computed calories logged from activity.
        actual_protein_g: Computed protein grams from meals.
        actual_carbs_g: Computed carbohydrate grams from meals.
        actual_fat_g: Computed fat grams from meals.
        net_calories: Food calories minus exercise calories.
        meals_count: Number of meals logged for the day.
        meal_items_count: Number of meal items logged for the day.
        activities_count: Number of activity entries logged for the day.
    """

    target_date: str
    target_food_calories: float | None
    target_exercise_calories: float | None
    target_protein_g: float | None
    target_carbs_g: float | None
    target_fat_g: float | None
    actual_food_calories: float
    actual_exercise_calories: float
    actual_protein_g: float
    actual_carbs_g: float
    actual_fat_g: float
    net_calories: float
    meals_count: int
    meal_items_count: int
    activities_count: int
