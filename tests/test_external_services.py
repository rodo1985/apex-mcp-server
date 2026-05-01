"""Tests for external service activity sync helpers."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

import httpx
import pytest

from apex_mcp_server.config import Settings, SettingsError
from apex_mcp_server.external_services import (
    STRAVA_API_BASE_URL,
    STRAVA_AUTHORIZE_URL,
    STRAVA_TOKEN_URL,
    StravaAPIError,
    build_strava_authorization_url,
    connect_strava_account,
    map_strava_activity_to_storage,
    resolve_strava_redirect_uri,
    resolve_sync_day,
    strava_connection_status,
    sync_external_service,
)


class FakeExternalActivityStore:
    """Small store double for external sync helper tests.

    Parameters:
        None.

    Returns:
        FakeExternalActivityStore: Store with only the upsert method used by
            `sync_external_service`.
    """

    def __init__(self) -> None:
        """Initialize the in-memory activity rows.

        Parameters:
            None.

        Returns:
            None.
        """

        self.rows: dict[tuple[str, str, str], dict[str, object]] = {}
        self.tokens: dict[tuple[str, str], dict[str, object]] = {}
        self.next_id = 1

    async def upsert_external_activity(
        self,
        subject: str,
        activity: dict[str, object],
    ) -> dict[str, object]:
        """Insert or update one externally sourced activity.

        Parameters:
            subject: Subject that owns the synced row.
            activity: Activity payload produced by the Strava mapper.

        Returns:
            dict[str, object]: Upsert result with action and stored item.
        """

        key = (
            subject,
            str(activity["external_source"]),
            str(activity["external_activity_id"]),
        )
        if key in self.rows:
            self.rows[key].update(activity)
            return {"action": "updated", "item": deepcopy(self.rows[key])}

        row = {"id": self.next_id, "subject": subject, **activity}
        self.next_id += 1
        self.rows[key] = row
        return {"action": "inserted", "item": deepcopy(row)}

    async def get_external_service_token(
        self,
        subject: str,
        service: str,
    ) -> dict[str, object] | None:
        """Return a saved token row for one subject and service.

        Parameters:
            subject: Subject that owns the token.
            service: External service name.

        Returns:
            dict[str, object] | None: Stored token row, or `None`.
        """

        row = self.tokens.get((subject, service))
        return deepcopy(row) if row is not None else None

    async def save_external_service_token(
        self,
        subject: str,
        service: str,
        access_token: str | None,
        refresh_token: str,
        expires_at: int | None,
        raw_payload: dict[str, object],
    ) -> dict[str, object]:
        """Store a token row for one subject and service.

        Parameters:
            subject: Subject that owns the token.
            service: External service name.
            access_token: Short-lived access token.
            refresh_token: Latest refresh token.
            expires_at: Optional token expiry Unix timestamp.
            raw_payload: Safe token metadata.

        Returns:
            dict[str, object]: Stored token row.
        """

        row = {
            "subject": subject,
            "service": service,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": expires_at,
            "raw_payload": raw_payload,
        }
        self.tokens[(subject, service)] = row
        return deepcopy(row)


def strava_settings() -> Settings:
    """Return settings with complete fake Strava credentials.

    Parameters:
        None.

    Returns:
        Settings: Runtime settings suitable for mocked Strava tests.
    """

    return Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
        strava_client_id="client-id",
        strava_client_secret="client-secret",
        strava_refresh_token="refresh-token",
    )


def test_resolve_sync_day_uses_europe_madrid_for_relative_days() -> None:
    """Ensure relative sync days use Europe/Madrid wellness dates.

    Parameters:
        None.

    Returns:
        None.
    """

    now = datetime(2026, 4, 29, 22, 30, tzinfo=ZoneInfo("UTC"))

    assert resolve_sync_day("today", now=now).isoformat() == "2026-04-30"
    assert resolve_sync_day("yesterday", now=now).isoformat() == "2026-04-29"
    assert resolve_sync_day("2026-04-28", now=now).isoformat() == "2026-04-28"


def test_resolve_sync_day_rejects_invalid_values() -> None:
    """Ensure invalid day strings fail with a clear validation error.

    Parameters:
        None.

    Returns:
        None.
    """

    with pytest.raises(ValueError, match="day must be"):
        resolve_sync_day("next week")


def test_strava_authorization_url_requests_activity_scope() -> None:
    """Ensure the browser connect URL asks Strava for activity access.

    Parameters:
        None.

    Returns:
        None.
    """

    settings = strava_settings()

    url = build_strava_authorization_url(settings, state="connect-test")
    parsed = httpx.URL(url)
    query = parse_qs(parsed.query.decode())

    assert str(parsed.copy_with(query=None)) == STRAVA_AUTHORIZE_URL
    assert query["client_id"] == ["client-id"]
    assert query["redirect_uri"] == ["http://localhost:8000/auth/strava/callback"]
    assert query["approval_prompt"] == ["force"]
    assert query["scope"] == ["read,activity:read_all"]
    assert query["state"] == ["connect-test"]


def test_strava_redirect_uri_uses_public_base_url_when_configured() -> None:
    """Ensure hosted deployments derive a callback URL from the public base URL.

    Parameters:
        None.

    Returns:
        None.
    """

    settings = Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url="https://apex.example.com/",
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
        strava_client_id="client-id",
        strava_client_secret="client-secret",
    )

    assert (
        resolve_strava_redirect_uri(settings)
        == "https://apex.example.com/auth/strava/callback"
    )


@pytest.mark.asyncio
async def test_connect_strava_account_exchanges_code_and_saves_token() -> None:
    """Ensure OAuth callback handling saves a token without returning secrets.

    Parameters:
        None.

    Returns:
        None.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a fake token exchange response.

        Parameters:
            request: Outgoing HTTP request made by the OAuth helper.

        Returns:
            httpx.Response: Mocked Strava token response.
        """

        assert str(request.url) == STRAVA_TOKEN_URL
        form = parse_qs(request.content.decode())
        assert form["code"] == ["oauth-code"]
        assert form["grant_type"] == ["authorization_code"]
        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token-from-code",
                "expires_at": 4_102_444_800,
                "expires_in": 21_600,
                "token_type": "Bearer",
                "scope": "read,activity:read_all",
                "athlete": {"id": 999},
            },
        )

    store = FakeExternalActivityStore()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await connect_strava_account(
            settings=strava_settings(),
            store=store,  # type: ignore[arg-type]
            code="oauth-code",
            granted_scope="read,activity:read_all",
            http_client=client,
        )

    stored_token = store.tokens[("strava-singleton", "strava")]

    assert summary == {
        "service": "strava",
        "status": "connected",
        "token_subject": "strava-singleton",
        "athlete_id": 999,
        "granted_scope": "read,activity:read_all",
        "expires_at": 4_102_444_800,
        "warnings": [],
    }
    assert stored_token["refresh_token"] == "refresh-token-from-code"
    assert "access-token" not in str(summary)
    assert "refresh-token-from-code" not in str(summary)


@pytest.mark.asyncio
async def test_connect_strava_account_warns_when_activity_scope_is_missing() -> None:
    """Ensure a read-only Strava connection explains why sync will fail.

    Parameters:
        None.

    Returns:
        None.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a fake read-only token response.

        Parameters:
            request: Outgoing HTTP request made by the OAuth helper.

        Returns:
            httpx.Response: Mocked Strava token response.
        """

        return httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_at": 4_102_444_800,
                "scope": "read",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await connect_strava_account(
            settings=strava_settings(),
            store=FakeExternalActivityStore(),  # type: ignore[arg-type]
            code="oauth-code",
            granted_scope="read",
            http_client=client,
        )

    warning_text = " ".join(str(item) for item in summary["warnings"])

    assert "activity:read" in warning_text


@pytest.mark.asyncio
async def test_sync_external_service_rejects_unsupported_services() -> None:
    """Ensure the v1 dispatcher only supports Strava.

    Parameters:
        None.

    Returns:
        None.
    """

    store = FakeExternalActivityStore()

    with pytest.raises(ValueError, match="Unsupported external service"):
        await sync_external_service(
            settings=strava_settings(),
            store=store,  # type: ignore[arg-type]
            subject="subject-1",
            service="coros",
            day="today",
        )


@pytest.mark.asyncio
async def test_sync_external_service_reports_missing_strava_config() -> None:
    """Ensure Strava sync fails lazily when Strava env vars are missing.

    Parameters:
        None.

    Returns:
        None.
    """

    settings = Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
    )

    with pytest.raises(SettingsError, match="Strava is not configured"):
        await sync_external_service(
            settings=settings,
            store=FakeExternalActivityStore(),  # type: ignore[arg-type]
            subject="subject-1",
            service="strava",
            day="2026-04-29",
        )


@pytest.mark.asyncio
async def test_sync_external_service_reports_missing_strava_connection() -> None:
    """Ensure missing token state tells the operator to connect Strava.

    Parameters:
        None.

    Returns:
        None.
    """

    settings = Settings(
        app_name="APEX FastMCP Profile Pilot",
        version="0.1.0",
        auth_mode="none",
        api_token=None,
        public_base_url=None,
        workos_authkit_domain=None,
        database_url="postgresql://demo:demo@localhost:5432/demo",
        strava_client_id="client-id",
        strava_client_secret="client-secret",
    )

    with pytest.raises(SettingsError, match="/auth/strava/start"):
        await sync_external_service(
            settings=settings,
            store=FakeExternalActivityStore(),  # type: ignore[arg-type]
            subject="subject-1",
            service="strava",
            day="2026-04-29",
        )


@pytest.mark.asyncio
async def test_strava_sync_reports_missing_activity_scope() -> None:
    """Ensure Strava activity-scope 401 responses are actionable.

    Parameters:
        None.

    Returns:
        None.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a valid token and an activity-scope failure.

        Parameters:
            request: Outgoing HTTP request made by the sync helper.

        Returns:
            httpx.Response: Mocked Strava API response.
        """

        if str(request.url) == STRAVA_TOKEN_URL:
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "refresh-token",
                    "expires_at": 4_102_444_800,
                },
            )

        if request.url.path == "/api/v3/athlete/activities":
            return httpx.Response(
                401,
                json={
                    "message": "Authorization Error",
                    "errors": [
                        {
                            "resource": "AccessToken",
                            "field": "activity:read_permission",
                            "code": "missing",
                        }
                    ],
                },
            )

        return httpx.Response(404, json={"message": "unexpected request"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(StravaAPIError, match="Reconnect Strava"):
            await sync_external_service(
                settings=strava_settings(),
                store=FakeExternalActivityStore(),  # type: ignore[arg-type]
                subject="subject-1",
                service="strava",
                day="2026-04-29",
                http_client=client,
            )


@pytest.mark.asyncio
async def test_strava_connection_status_is_safe_and_actionable() -> None:
    """Ensure the diagnostic status reports presence without leaking values.

    Parameters:
        None.

    Returns:
        None.
    """

    store = FakeExternalActivityStore()
    await store.save_external_service_token(
        subject="strava-singleton",
        service="strava",
        access_token="access-token",
        refresh_token="refresh-token",
        expires_at=4_102_444_800,
        raw_payload={},
    )

    status = await strava_connection_status(
        settings=strava_settings(),
        store=store,  # type: ignore[arg-type]
    )

    assert status["client_id"] == "present"
    assert status["client_secret"] == "present"
    assert status["env_refresh_token"] == "present"
    assert status["stored_token"] == "present"
    assert status["activity_scope"] == "present"
    assert "access-token" not in str(status)
    assert "refresh-token" not in str(status)


def test_map_strava_activity_to_storage_captures_expected_fields() -> None:
    """Ensure Strava details map into the existing activity row shape.

    Parameters:
        None.

    Returns:
        None.
    """

    mapped = map_strava_activity_to_storage(
        {
            "id": 123,
            "name": "Morning ride",
            "start_date_local": "2026-04-29T07:15:00Z",
            "athlete": {"id": 456},
            "sport_type": "Ride",
            "distance": 54000.0,
            "moving_time": 7200,
            "elapsed_time": 7500,
            "total_elevation_gain": 850.0,
            "average_speed": 7.5,
            "max_speed": 15.0,
            "average_heartrate": 138.0,
            "max_heartrate": 176.0,
            "average_watts": 210.0,
            "weighted_average_watts": 225.0,
            "calories": 700.0,
            "kilojoules": 1500.0,
            "suffer_score": 110.0,
            "trainer": False,
            "commute": False,
            "manual": True,
            "visibility": "only_me",
            "laps": [{"name": "Lap 1"}],
            "zones": {"heartrate": []},
            "streams": {"heartrate": [120, 130]},
        },
        fallback_date=resolve_sync_day("2026-04-29"),
    )

    assert mapped["activity_date"] == "2026-04-29"
    assert mapped["title"] == "Morning ride"
    assert mapped["external_source"] == "strava"
    assert mapped["external_activity_id"] == "123"
    assert mapped["athlete_id"] == "456"
    assert mapped["manual"] is True
    assert mapped["is_private"] is True
    assert mapped["calories"] == 700.0
    assert mapped["raw_payload"] is not None


@pytest.mark.asyncio
async def test_strava_sync_fetches_details_and_upserts_idempotently() -> None:
    """Ensure mocked Strava sync stores one activity and updates on re-sync.

    Parameters:
        None.

    Returns:
        None.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return fake Strava responses for the sync request sequence.

        Parameters:
            request: Outgoing HTTP request made by the sync helper.

        Returns:
            httpx.Response: Mocked Strava API response.
        """

        if str(request.url) == STRAVA_TOKEN_URL:
            return httpx.Response(
                200,
                json={
                    "access_token": "access-token",
                    "refresh_token": "rotated-refresh-token",
                    "expires_at": 4_102_444_800,
                    "expires_in": 21_600,
                    "token_type": "Bearer",
                },
            )

        if request.url.path == "/api/v3/athlete/activities":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": 111,
                        "name": "Morning run",
                        "start_date_local": "2026-04-29T08:00:00Z",
                    },
                    {
                        "id": 222,
                        "name": "Boundary skip",
                        "start_date_local": "2026-04-30T00:05:00Z",
                    },
                ],
            )

        if str(request.url) == f"{STRAVA_API_BASE_URL}/activities/111":
            return httpx.Response(
                200,
                json={
                    "id": 111,
                    "name": "Morning run",
                    "start_date_local": "2026-04-29T08:00:00Z",
                    "athlete": {"id": 999},
                    "sport_type": "Run",
                    "distance": 10000.0,
                    "moving_time": 2700,
                    "elapsed_time": 2800,
                    "calories": 600.0,
                    "manual": False,
                    "private": False,
                },
            )

        return httpx.Response(404, json={"message": "unexpected request"})

    store = FakeExternalActivityStore()
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        first_summary = await sync_external_service(
            settings=strava_settings(),
            store=store,  # type: ignore[arg-type]
            subject="subject-1",
            service="strava",
            day="2026-04-29",
            http_client=client,
        )
        second_summary = await sync_external_service(
            settings=strava_settings(),
            store=store,  # type: ignore[arg-type]
            subject="subject-1",
            service="strava",
            day="2026-04-29",
            http_client=client,
        )

    warning_text = " ".join(str(item) for item in first_summary["warnings"])
    stored_row = next(iter(store.rows.values()))

    assert first_summary["fetched_count"] == 2
    assert first_summary["inserted_count"] == 1
    assert first_summary["updated_count"] == 0
    assert first_summary["skipped_count"] == 1
    assert first_summary["activity_ids"] == [1]
    stored_token = store.tokens[("strava-singleton", "strava")]

    assert "rotated" in warning_text
    assert "rotated-refresh-token" not in warning_text
    assert second_summary["inserted_count"] == 0
    assert second_summary["updated_count"] == 1
    assert len(store.rows) == 1
    assert stored_token["access_token"] == "access-token"
    assert stored_token["refresh_token"] == "rotated-refresh-token"
    assert stored_token["raw_payload"] == {
        "token_type": "Bearer",
        "expires_at": 4_102_444_800,
        "expires_in": 21_600,
    }
    assert stored_row["title"] == "Morning run"
    assert stored_row["calories"] == 600.0


@pytest.mark.asyncio
async def test_strava_sync_retries_env_token_when_stored_token_is_rejected() -> None:
    """Ensure a stale stored refresh token can recover from the env seed.

    Parameters:
        None.

    Returns:
        None.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        """Return a 401 for stale DB token and success for env token.

        Parameters:
            request: Outgoing HTTP request made by the sync helper.

        Returns:
            httpx.Response: Mocked Strava API response.
        """

        if str(request.url) == STRAVA_TOKEN_URL:
            form = parse_qs(request.content.decode())
            refresh_token = form["refresh_token"][0]
            if refresh_token == "stale-db-token":
                return httpx.Response(401, json={"message": "Authorization Error"})
            return httpx.Response(
                200,
                json={
                    "access_token": "env-access-token",
                    "refresh_token": "env-refresh-token-rotated",
                    "expires_at": 4_102_444_800,
                },
            )

        if request.url.path == "/api/v3/athlete/activities":
            return httpx.Response(200, json=[])

        return httpx.Response(404, json={"message": "unexpected request"})

    store = FakeExternalActivityStore()
    await store.save_external_service_token(
        subject="strava-singleton",
        service="strava",
        access_token="old-access-token",
        refresh_token="stale-db-token",
        expires_at=0,
        raw_payload={},
    )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        summary = await sync_external_service(
            settings=strava_settings(),
            store=store,  # type: ignore[arg-type]
            subject="subject-1",
            service="strava",
            day="2026-04-29",
            http_client=client,
        )

    warning_text = " ".join(str(item) for item in summary["warnings"])
    stored_token = store.tokens[("strava-singleton", "strava")]

    assert "Stored Strava refresh token was rejected" in warning_text
    assert "stale-db-token" not in warning_text
    assert stored_token["access_token"] == "env-access-token"
    assert stored_token["refresh_token"] == "env-refresh-token-rotated"
    assert summary["fetched_count"] == 0
