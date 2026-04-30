"""External activity service sync helpers for the APEX MCP server."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from apex_mcp_server.config import Settings, SettingsError
from apex_mcp_server.storage import UserStore

LOCAL_TIME_ZONE = ZoneInfo("Europe/Madrid")
STRAVA_API_BASE_URL = "https://www.strava.com/api/v3"
STRAVA_SOURCE = "strava"
STRAVA_TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"


class StravaAPIError(RuntimeError):
    """Raised when Strava returns an unsuccessful HTTP response.

    Parameters:
        message: Safe error message that does not include token values.
        status_code: HTTP status code returned by Strava.

    Returns:
        StravaAPIError: Exception carrying the Strava HTTP status code.

    Raises:
        This initializer does not raise errors directly.
    """

    def __init__(self, message: str, status_code: int) -> None:
        """Store the safe error message and Strava HTTP status code.

        Parameters:
            message: Safe error message that does not include token values.
            status_code: HTTP status code returned by Strava.

        Returns:
            None.
        """

        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class StravaCredentials:
    """Store the Strava credentials needed for one sync call.

    Parameters:
        client_id: Strava application client id.
        client_secret: Strava application client secret.
        refresh_token: Optional env-seeded Strava refresh token used when no
            stored token exists or when a stored token has been replaced.

    Returns:
        StravaCredentials: Normalized credentials read from runtime settings.

    Raises:
        This dataclass does not raise errors directly.
    """

    client_id: str
    client_secret: str
    refresh_token: str | None


@dataclass(frozen=True, slots=True)
class StravaTokenResponse:
    """Store a refreshed Strava token response.

    Parameters:
        access_token: Short-lived access token used for activity API calls.
        refresh_token: Latest refresh token that must be persisted.
        expires_at: Unix timestamp when `access_token` expires.
        raw_payload: Safe metadata from Strava's token response.

    Returns:
        StravaTokenResponse: Parsed token response from Strava.

    Raises:
        This dataclass does not raise errors directly.
    """

    access_token: str
    refresh_token: str
    expires_at: int | None
    raw_payload: dict[str, object]


async def sync_external_service(
    settings: Settings,
    store: UserStore,
    subject: str,
    service: str,
    day: str,
    http_client: httpx.AsyncClient | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    """Sync one supported external service into the caller's activity log.

    Parameters:
        settings: Runtime settings containing optional service credentials.
        store: User storage backend where mapped activities are upserted.
        subject: Storage subject for the current MCP caller.
        service: External service name. Only `strava` is supported in v1.
        day: Requested day: `today`, `yesterday`, or an ISO `YYYY-MM-DD`.
        http_client: Optional HTTP client supplied by tests.
        now: Optional current time override used by tests for relative days.

    Returns:
        dict[str, object]: Sync summary with counts, stored ids, and warnings.

    Raises:
        ValueError: If the service or day value is unsupported.
        SettingsError: If Strava sync is requested without Strava credentials.
        RuntimeError: If Strava returns an invalid or failing response.

    Example:
        >>> # Called by the MCP tool after resolving the request identity.
        >>> # await sync_external_service(settings, store, "me", "strava", "today")
    """

    normalized_service = service.strip().lower()
    if normalized_service != STRAVA_SOURCE:
        raise ValueError(
            "Unsupported external service "
            f"'{service}'. Supported services: {STRAVA_SOURCE}."
        )

    resolved_day = resolve_sync_day(day, now=now)
    return await sync_strava_activities(
        settings=settings,
        store=store,
        subject=subject,
        requested_day=day,
        resolved_day=resolved_day,
        http_client=http_client,
    )


def resolve_sync_day(day: str, now: datetime | None = None) -> date:
    """Resolve a user-facing day string into a Europe/Madrid calendar date.

    Parameters:
        day: Requested day: `today`, `yesterday`, or an ISO `YYYY-MM-DD`.
        now: Optional current time override, mainly used by tests.

    Returns:
        date: Concrete wellness day in the Europe/Madrid time zone.

    Raises:
        ValueError: If `day` is empty or not one of the supported forms.

    Example:
        >>> resolve_sync_day("2026-04-29").isoformat()
        '2026-04-29'
    """

    requested = day.strip().lower()
    current_time = now or datetime.now(tz=LOCAL_TIME_ZONE)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=LOCAL_TIME_ZONE)
    local_today = current_time.astimezone(LOCAL_TIME_ZONE).date()

    if requested == "today":
        return local_today
    if requested == "yesterday":
        return local_today - timedelta(days=1)

    try:
        return date.fromisoformat(requested)
    except ValueError as exc:
        raise ValueError(
            "day must be 'today', 'yesterday', or an ISO date like 2026-04-29."
        ) from exc


async def sync_strava_activities(
    settings: Settings,
    store: UserStore,
    subject: str,
    requested_day: str,
    resolved_day: date,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, object]:
    """Fetch Strava activities for one day and upsert them into storage.

    Parameters:
        settings: Runtime settings containing Strava credentials.
        store: User storage backend where activity rows are saved.
        subject: Storage subject for the current MCP caller.
        requested_day: Original day string provided by the caller.
        resolved_day: Concrete Europe/Madrid calendar date to sync.
        http_client: Optional HTTP client supplied by tests.

    Returns:
        dict[str, object]: Agent-facing sync summary.

    Raises:
        SettingsError: If required Strava credentials are missing.
        RuntimeError: If Strava token refresh, listing, or detail loading fails.
        Exception: Propagated from the storage backend when upserts fail.
    """

    credentials = _require_strava_credentials(settings)
    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=30.0)
    warnings: list[str] = []

    try:
        access_token, token_warnings = await _get_valid_strava_access_token(
            settings=settings,
            store=store,
            subject=subject,
            client=client,
            credentials=credentials,
        )
        warnings.extend(token_warnings)

        summaries = await _list_strava_activity_summaries(
            client,
            access_token,
            resolved_day,
        )

        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        stored_activity_ids: list[object] = []

        for summary in summaries:
            external_activity_id = _string_value(summary.get("id"))
            summary_date = _strava_start_local_date(summary)
            if external_activity_id is None:
                skipped_count += 1
                warnings.append("Skipped one Strava activity because it had no id.")
                continue
            if summary_date != resolved_day:
                skipped_count += 1
                continue

            detail = await _get_strava_activity_detail(
                client,
                access_token,
                external_activity_id,
            )
            detail_date = _strava_start_local_date(detail) or summary_date
            if detail_date != resolved_day:
                skipped_count += 1
                continue

            activity_payload = map_strava_activity_to_storage(
                detail,
                fallback_date=resolved_day,
            )
            result = await store.upsert_external_activity(subject, activity_payload)
            action = result["action"]
            item = result["item"]
            if action == "inserted":
                inserted_count += 1
            else:
                updated_count += 1
            if isinstance(item, dict):
                stored_id = item.get("id")
                if stored_id is not None:
                    stored_activity_ids.append(stored_id)

        return {
            "service": STRAVA_SOURCE,
            "requested_day": requested_day,
            "resolved_date": resolved_day.isoformat(),
            "fetched_count": len(summaries),
            "inserted_count": inserted_count,
            "updated_count": updated_count,
            "skipped_count": skipped_count,
            "activity_ids": stored_activity_ids,
            "warnings": warnings,
        }
    finally:
        if owns_client:
            await client.aclose()


def map_strava_activity_to_storage(
    activity: dict[str, Any],
    fallback_date: date,
) -> dict[str, object]:
    """Map one Strava activity payload into the existing activity row shape.

    Parameters:
        activity: Strava detailed activity payload.
        fallback_date: Date to use if Strava omits `start_date_local`.

    Returns:
        dict[str, object]: Keyword-style activity payload accepted by storage.

    Raises:
        ValueError: If the Strava payload is missing its activity id.
    """

    external_activity_id = _string_value(activity.get("id"))
    if external_activity_id is None:
        raise ValueError("Strava activity payload is missing id.")

    activity_date = _strava_start_local_date(activity) or fallback_date
    title = (
        _string_value(activity.get("name"))
        or f"Strava activity {external_activity_id}"
    )
    athlete_id = _strava_athlete_id(activity.get("athlete"))
    visibility = _string_value(activity.get("visibility"))

    return {
        "activity_date": activity_date.isoformat(),
        "title": title,
        "external_source": STRAVA_SOURCE,
        "external_activity_id": external_activity_id,
        "athlete_id": athlete_id,
        "sport_type": _string_value(activity.get("sport_type"))
        or _string_value(activity.get("type")),
        "distance_meters": _float_value(activity.get("distance")),
        "moving_time_seconds": _int_value(activity.get("moving_time")),
        "elapsed_time_seconds": _int_value(activity.get("elapsed_time")),
        "total_elevation_gain_meters": _float_value(
            activity.get("total_elevation_gain")
        ),
        "average_speed_mps": _float_value(activity.get("average_speed")),
        "max_speed_mps": _float_value(activity.get("max_speed")),
        "average_heartrate": _float_value(activity.get("average_heartrate")),
        "max_heartrate": _float_value(activity.get("max_heartrate")),
        "average_watts": _float_value(activity.get("average_watts")),
        "weighted_average_watts": _float_value(
            activity.get("weighted_average_watts")
        ),
        "calories": _float_value(activity.get("calories")),
        "kilojoules": _float_value(activity.get("kilojoules")),
        "suffer_score": _float_value(activity.get("suffer_score")),
        "trainer": _bool_value(activity.get("trainer"), default=False),
        "commute": _bool_value(activity.get("commute"), default=False),
        "manual": _bool_value(activity.get("manual"), default=False),
        "is_private": _bool_value(activity.get("private"), default=False)
        or visibility in {"followers_only", "only_me"},
        "zones": _dict_value(activity.get("zones")),
        "laps": _list_of_dicts(activity.get("laps")),
        "streams": _dict_value(activity.get("streams")),
        "raw_payload": activity,
        "notes_markdown": "Imported from Strava.",
    }


def _require_strava_credentials(settings: Settings) -> StravaCredentials:
    """Return Strava client credentials and optional env refresh-token seed.

    Parameters:
        settings: Runtime settings to inspect.

    Returns:
        StravaCredentials: Strava API configuration.

    Raises:
        SettingsError: If Strava client id or secret is missing.
    """

    missing = [
        name
        for name, value in {
            "STRAVA_CLIENT_ID": settings.strava_client_id,
            "STRAVA_CLIENT_SECRET": settings.strava_client_secret,
        }.items()
        if value is None
    ]
    if missing:
        raise SettingsError(
            "Strava sync requires STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET."
        )

    return StravaCredentials(
        client_id=str(settings.strava_client_id),
        client_secret=str(settings.strava_client_secret),
        refresh_token=settings.strava_refresh_token,
    )


async def _get_valid_strava_access_token(
    settings: Settings,
    store: UserStore,
    subject: str,
    client: httpx.AsyncClient,
    credentials: StravaCredentials,
) -> tuple[str, list[str]]:
    """Return a usable Strava access token and persist any rotated token.

    Parameters:
        settings: Runtime settings with the env refresh-token seed.
        store: User storage backend used for persisted token bundles.
        subject: Storage subject for the current MCP caller.
        client: HTTP client used for Strava API requests.
        credentials: Strava client credentials and optional env token seed.

    Returns:
        tuple[str, list[str]]: Access token plus non-secret sync warnings.

    Raises:
        SettingsError: If neither Postgres nor env contains a refresh token.
        RuntimeError: If Strava rejects all available refresh tokens.
    """

    warnings: list[str] = []
    stored_token = await store.get_external_service_token(subject, STRAVA_SOURCE)
    stored_access_token = _string_value(
        stored_token.get("access_token") if stored_token else None
    )
    stored_refresh_token = _string_value(
        stored_token.get("refresh_token") if stored_token else None
    )
    stored_expires_at = _int_value(
        stored_token.get("expires_at") if stored_token else None
    )
    now_ts = int(datetime.now(tz=UTC).timestamp())

    if (
        stored_access_token is not None
        and stored_expires_at is not None
        and stored_expires_at > now_ts + 120
    ):
        return stored_access_token, warnings

    refresh_candidates = _refresh_token_candidates(
        stored_refresh_token,
        credentials.refresh_token,
    )
    if not refresh_candidates:
        raise SettingsError(
            "Strava sync requires STRAVA_REFRESH_TOKEN until the first "
            "successful token refresh is stored in Postgres."
        )

    last_error: StravaAPIError | None = None
    for source, refresh_token in refresh_candidates:
        try:
            refreshed = await _refresh_strava_access_token(
                client,
                credentials,
                refresh_token,
            )
        except StravaAPIError as exc:
            last_error = exc
            if exc.status_code == 401 and source == "stored":
                warnings.append(
                    "Stored Strava refresh token was rejected; retrying with "
                    "the environment refresh token seed."
                )
                continue
            raise

        await store.save_external_service_token(
            subject=subject,
            service=STRAVA_SOURCE,
            access_token=refreshed.access_token,
            refresh_token=refreshed.refresh_token,
            expires_at=refreshed.expires_at,
            raw_payload=refreshed.raw_payload,
        )
        if refreshed.refresh_token != refresh_token:
            warnings.append("Strava rotated the refresh token and saved it.")
        return refreshed.access_token, warnings

    if last_error is not None:
        raise last_error
    raise RuntimeError("Strava token refresh failed before returning a token.")


async def _refresh_strava_access_token(
    client: httpx.AsyncClient,
    credentials: StravaCredentials,
    refresh_token: str,
) -> StravaTokenResponse:
    """Refresh the Strava access token for the current sync call.

    Parameters:
        client: HTTP client used for the token request.
        credentials: Strava credentials read from settings.
        refresh_token: Latest refresh token available for the subject.

    Returns:
        StravaTokenResponse: Parsed token response to use and persist.

    Raises:
        RuntimeError: If Strava returns an error or no access token.
    """

    response = await client.post(
        STRAVA_TOKEN_URL,
        data={
            "client_id": credentials.client_id,
            "client_secret": credentials.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    _raise_for_strava_status(response, "token refresh")
    payload = _json_dict(response, "token refresh")

    access_token = _string_value(payload.get("access_token"))
    if access_token is None:
        raise RuntimeError("Strava token refresh did not return an access token.")

    new_refresh_token = _string_value(payload.get("refresh_token"))
    if new_refresh_token is None:
        raise RuntimeError("Strava token refresh did not return a refresh token.")

    return StravaTokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_at=_int_value(payload.get("expires_at")),
        raw_payload=_safe_token_payload(payload),
    )


def _refresh_token_candidates(
    stored_refresh_token: str | None,
    env_refresh_token: str | None,
) -> list[tuple[str, str]]:
    """Return refresh-token candidates in retry order without duplicates.

    Parameters:
        stored_refresh_token: Latest refresh token saved in Postgres.
        env_refresh_token: Environment refresh-token seed.

    Returns:
        list[tuple[str, str]]: `(source, token)` pairs to try.

    Raises:
        This helper does not raise errors directly.
    """

    candidates: list[tuple[str, str]] = []
    if stored_refresh_token:
        candidates.append(("stored", stored_refresh_token))
    if env_refresh_token and env_refresh_token != stored_refresh_token:
        candidates.append(("env", env_refresh_token))
    return candidates


async def _list_strava_activity_summaries(
    client: httpx.AsyncClient,
    access_token: str,
    target_day: date,
) -> list[dict[str, Any]]:
    """List Strava activity summaries that may overlap one local day.

    Parameters:
        client: HTTP client used for Strava API requests.
        access_token: Short-lived Strava access token.
        target_day: Europe/Madrid wellness day being synced.

    Returns:
        list[dict[str, Any]]: Raw Strava activity summaries.

    Raises:
        RuntimeError: If Strava returns an error or unexpected payload.
    """

    after_epoch, before_epoch = _local_day_epoch_window(target_day)
    activities: list[dict[str, Any]] = []
    page = 1

    while True:
        response = await client.get(
            f"{STRAVA_API_BASE_URL}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "after": after_epoch,
                "before": before_epoch,
                "page": page,
                "per_page": 100,
            },
        )
        _raise_for_strava_status(response, "activity list")
        payload = _json_list(response, "activity list")

        page_items = [item for item in payload if isinstance(item, dict)]
        activities.extend(page_items)
        if len(payload) < 100:
            return activities
        page += 1


async def _get_strava_activity_detail(
    client: httpx.AsyncClient,
    access_token: str,
    activity_id: str,
) -> dict[str, Any]:
    """Load one detailed Strava activity payload.

    Parameters:
        client: HTTP client used for Strava API requests.
        access_token: Short-lived Strava access token.
        activity_id: Strava activity id to load.

    Returns:
        dict[str, Any]: Detailed Strava activity payload.

    Raises:
        RuntimeError: If Strava returns an error or unexpected payload.
    """

    response = await client.get(
        f"{STRAVA_API_BASE_URL}/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    _raise_for_strava_status(response, "activity detail")
    return _json_dict(response, "activity detail")


def _local_day_epoch_window(target_day: date) -> tuple[int, int]:
    """Return epoch bounds for a Europe/Madrid local calendar day.

    Parameters:
        target_day: Local calendar date to convert into Strava query bounds.

    Returns:
        tuple[int, int]: `(after, before)` epoch seconds for Strava filtering.

    Raises:
        This helper does not raise errors directly.
    """

    start = datetime.combine(target_day, time.min, tzinfo=LOCAL_TIME_ZONE)
    end = start + timedelta(days=1)
    # Strava's `after` filter is easier to reason about when an activity that
    # starts exactly at local midnight cannot fall through a strict boundary.
    return int(start.timestamp()) - 1, int(end.timestamp())


def _strava_start_local_date(activity: dict[str, Any]) -> date | None:
    """Extract the local Strava start date from an activity payload.

    Parameters:
        activity: Strava summary or detail payload.

    Returns:
        date | None: Parsed local date, or `None` when unavailable.

    Raises:
        This helper does not raise errors directly.
    """

    raw_start = _string_value(activity.get("start_date_local"))
    if raw_start is None or len(raw_start) < 10:
        return None

    try:
        return date.fromisoformat(raw_start[:10])
    except ValueError:
        return None


def _strava_athlete_id(athlete: object) -> str | None:
    """Extract a Strava athlete id from the nested athlete payload.

    Parameters:
        athlete: Raw `athlete` value from a Strava activity.

    Returns:
        str | None: Athlete id string when present.

    Raises:
        This helper does not raise errors directly.
    """

    if not isinstance(athlete, dict):
        return None
    return _string_value(athlete.get("id"))


def _raise_for_strava_status(response: httpx.Response, operation: str) -> None:
    """Raise a safe Strava error message for non-success HTTP responses.

    Parameters:
        response: Strava HTTP response to inspect.
        operation: Human-readable operation name for diagnostics.

    Returns:
        None: Successful responses pass through.

    Raises:
        RuntimeError: If the response status is not successful.
    """

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise StravaAPIError(
            f"Strava {operation} failed with HTTP {response.status_code}.",
            response.status_code,
        ) from exc


def _json_dict(response: httpx.Response, operation: str) -> dict[str, Any]:
    """Parse a Strava JSON object response.

    Parameters:
        response: HTTP response returned by Strava.
        operation: Human-readable operation name for diagnostics.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        RuntimeError: If the response body is not a JSON object.
    """

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Strava {operation} returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Strava {operation} returned an unexpected payload.")
    return payload


def _json_list(response: httpx.Response, operation: str) -> list[object]:
    """Parse a Strava JSON list response.

    Parameters:
        response: HTTP response returned by Strava.
        operation: Human-readable operation name for diagnostics.

    Returns:
        list[object]: Parsed JSON list.

    Raises:
        RuntimeError: If the response body is not a JSON list.
    """

    try:
        payload = response.json()
    except ValueError as exc:
        raise RuntimeError(f"Strava {operation} returned invalid JSON.") from exc
    if not isinstance(payload, list):
        raise RuntimeError(f"Strava {operation} returned an unexpected payload.")
    return payload


def _safe_token_payload(payload: dict[str, Any]) -> dict[str, object]:
    """Return token response metadata without duplicating secret token values.

    Parameters:
        payload: Raw Strava token refresh response.

    Returns:
        dict[str, object]: Non-secret metadata safe to store for diagnostics.

    Raises:
        This helper does not raise errors directly.
    """

    safe_payload: dict[str, object] = {}
    for key in ("token_type", "expires_at", "expires_in", "scope"):
        if key in payload:
            safe_payload[key] = payload[key]
    athlete = payload.get("athlete")
    if isinstance(athlete, dict) and "id" in athlete:
        safe_payload["athlete_id"] = athlete["id"]
    return safe_payload


def _string_value(value: object | None) -> str | None:
    """Normalize a nullable scalar value into a non-empty string.

    Parameters:
        value: Raw value to normalize.

    Returns:
        str | None: Trimmed string value, or `None` when empty.

    Raises:
        This helper does not raise errors directly.
    """

    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None


def _float_value(value: object | None) -> float | None:
    """Normalize a nullable Strava numeric value into a float.

    Parameters:
        value: Raw value to normalize.

    Returns:
        float | None: Float value, or `None` when unavailable.

    Raises:
        This helper does not raise errors directly.
    """

    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_value(value: object | None) -> int | None:
    """Normalize a nullable Strava integer value.

    Parameters:
        value: Raw value to normalize.

    Returns:
        int | None: Integer value, or `None` when unavailable.

    Raises:
        This helper does not raise errors directly.
    """

    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _bool_value(value: object | None, default: bool) -> bool:
    """Normalize a nullable Strava boolean value.

    Parameters:
        value: Raw value to normalize.
        default: Value to use when Strava omits the field.

    Returns:
        bool: Normalized boolean.

    Raises:
        This helper does not raise errors directly.
    """

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return bool(value)


def _dict_value(value: object | None) -> dict[str, object] | None:
    """Return a JSON object only when the raw value is dictionary-shaped.

    Parameters:
        value: Raw value to normalize.

    Returns:
        dict[str, object] | None: Dictionary value or `None`.

    Raises:
        This helper does not raise errors directly.
    """

    if isinstance(value, dict):
        return value
    return None


def _list_of_dicts(value: object | None) -> list[dict[str, object]] | None:
    """Return a JSON list only when every item is dictionary-shaped.

    Parameters:
        value: Raw value to normalize.

    Returns:
        list[dict[str, object]] | None: List of dictionaries or `None`.

    Raises:
        This helper does not raise errors directly.
    """

    if not isinstance(value, list):
        return None
    if not all(isinstance(item, dict) for item in value):
        return None
    return value
