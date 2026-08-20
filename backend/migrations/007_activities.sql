-- Actividad física. Manual y Whoop comparten tabla: las columnas encajan con
-- lo que devuelve /v2/activity/workout para que conectar la pulsera sea un
-- mapeo y no una migración.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/007_activities.sql

BEGIN;

CREATE TABLE IF NOT EXISTS activities (
    id            SERIAL PRIMARY KEY,
    source        VARCHAR(10)  NOT NULL DEFAULT 'manual',
    external_id   VARCHAR(64)  UNIQUE,
    activity_type VARCHAR(20)  NOT NULL DEFAULT 'other',
    sport_name    VARCHAR(120),
    started_at    TIMESTAMPTZ  NOT NULL,
    duration_min  INTEGER,
    calories      DOUBLE PRECISION,
    feeling       INTEGER,
    notes         TEXT,
    metrics       JSON,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_activities_started_at  ON activities (started_at);
CREATE INDEX IF NOT EXISTS ix_activities_external_id ON activities (external_id);

COMMIT;
