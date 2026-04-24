# Daily Wellness Metrics

This feature stores small date-scoped wellness values for trend tracking. It is meant for simple daily check-ins such as body weight, step count, and sleep duration without adding a new table or MCP tool for each metric type.

## Purpose

The APEX pilot already has singleton body data in `user_data` and computed nutrition summaries in `get_daily_summary`. `daily_metrics` fills the gap for repeated day-by-day values that an agent may want to inspect later, such as "show my weight trend" or "how did sleep look this week?"

It stays intentionally small:

- one generic `daily_metrics` table
- one grouped MCP tool
- no charts, forecasting, analytics jobs, or summary rollups

## Workflow

```mermaid
flowchart LR
    Caller["MCP caller"] --> Tool["daily_metrics tool"]
    Tool --> Validate["Validate metric_type and value"]
    Validate --> Store["daily_metrics table"]
    Store --> Trend["list/get responses for trend tracking"]
```

## Tool Operations

Use `daily_metrics` with one of four operations:

- `set`: upsert one metric value for a caller, date, and metric type
- `get`: read one metric value for a caller, date, and metric type
- `list`: list metric rows, optionally filtered by date range and metric type
- `delete`: remove one metric value for a caller, date, and metric type

Example calls:

```text
daily_metrics(operation="set", metric_date="2026-04-14", metric_type="weight", value=68.5)
daily_metrics(operation="set", metric_date="2026-04-14", metric_type="steps", value=12000)
daily_metrics(operation="set", metric_date="2026-04-14", metric_type="sleep_hours", value=7.5)
daily_metrics(operation="list", date_from="2026-04-01", date_to="2026-04-30", metric_type="weight")
```

Re-logging the same caller, date, and metric type updates the existing row instead of creating a duplicate.

## Data Model

The table is generic by metric type:

```text
daily_metrics
- id
- subject
- metric_date
- metric_type
- value
- created_at
- updated_at
```

The unique key is `(subject, metric_date, metric_type)`. The app bootstraps this additive schema on first successful database connection. For local Docker databases, the same table is also present in `docker/postgres/init/001_schema.sql`.

If a remote database user cannot create tables automatically, run the `daily_metrics` SQL block from `docker/postgres/init/001_schema.sql` manually in Supabase or your Postgres provider.

## Validation

Supported metric types:

- `weight`: finite number greater than `0`
- `steps`: finite whole number greater than or equal to `0`
- `sleep_hours`: finite number from `0` through `24`

Metric types are trimmed and lowercased before validation, so `Weight` and ` weight ` are stored as `weight`.

## Boundaries

`daily_metrics` is not included in `get_daily_summary`. The summary tool remains focused on planned targets, logged meals, and activities. This keeps the pilot easy to explain and prevents one generic metric table from turning into an analytics subsystem.
