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
    notes_markdown TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (subject, name)
);

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
