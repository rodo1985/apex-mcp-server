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
