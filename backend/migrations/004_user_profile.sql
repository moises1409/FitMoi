-- Perfil del usuario que construye el entrenador conversacional.
--
-- Aplicar una sola vez:
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/004_user_profile.sql

BEGIN;

CREATE TABLE IF NOT EXISTS user_profiles (
    id                     SERIAL PRIMARY KEY,
    age                    INTEGER,
    sex                    VARCHAR(10),
    weight_kg              DOUBLE PRECISION,
    height_cm              DOUBLE PRECISION,
    training_days_per_week INTEGER,
    activity_level         VARCHAR(20),
    job_activity           VARCHAR(20),
    job                    TEXT,
    location               TEXT,
    sports                 JSON,
    goals                  JSON,
    challenges             JSON,
    conditions             JSON,
    injuries_current       JSON,
    injuries_past          JSON,
    diet_notes             JSON,
    primary_goal           TEXT,
    free_notes             TEXT,
    conversation           JSON,
    completed              BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
