-- Resumen semanal (lunes→domingo) de nutrición y actividad. Una fila por semana
-- con clave natural (iso_year, iso_week). `metrics` congela las cifras de la
-- semana; `narrative` guarda lo que redacta el LLM sobre ellas. Regenerar
-- corrige la misma fila en vez de duplicarla.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/009_weekly_reviews.sql

BEGIN;

CREATE TABLE IF NOT EXISTS weekly_reviews (
    id           SERIAL PRIMARY KEY,
    iso_year     INTEGER     NOT NULL,
    iso_week     INTEGER     NOT NULL,
    week_start   DATE        NOT NULL,
    week_end     DATE        NOT NULL,
    metrics      JSON,
    narrative    JSON,
    model        VARCHAR(60),
    generated_at TIMESTAMPTZ,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_weekly_reviews_isoweek
    ON weekly_reviews (iso_year, iso_week);
CREATE INDEX IF NOT EXISTS ix_weekly_reviews_week_start
    ON weekly_reviews (week_start);

COMMIT;
