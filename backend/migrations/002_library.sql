-- Biblioteca de platos/alimentos reutilizables + composición de la comida.
--
-- Aplicar una sola vez:
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/002_library.sql
--
-- (db.create_all() crea food_templates por sí solo, pero no añade la columna
--  food_logs.items a una tabla que ya existe.)

BEGIN;

CREATE TABLE IF NOT EXISTS food_templates (
    id               SERIAL PRIMARY KEY,
    kind             VARCHAR(10)  NOT NULL DEFAULT 'dish',
    name             VARCHAR(200) NOT NULL,
    normalized_name  VARCHAR(200) NOT NULL UNIQUE,
    quantity_label   VARCHAR(80)  DEFAULT '',
    calories         DOUBLE PRECISION NOT NULL DEFAULT 0,
    proteins         DOUBLE PRECISION NOT NULL DEFAULT 0,
    carbs            DOUBLE PRECISION NOT NULL DEFAULT 0,
    fats             DOUBLE PRECISION NOT NULL DEFAULT 0,
    fiber            DOUBLE PRECISION NOT NULL DEFAULT 0,
    components       JSON,
    photo_path       VARCHAR(255),
    source           VARCHAR(10)  NOT NULL DEFAULT 'ai',
    times_used       INTEGER      NOT NULL DEFAULT 0,
    meal_type_counts JSON,
    last_used_at     TIMESTAMPTZ,
    archived         BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_food_templates_normalized_name ON food_templates (normalized_name);
CREATE INDEX IF NOT EXISTS ix_food_templates_last_used_at    ON food_templates (last_used_at);

ALTER TABLE food_logs ADD COLUMN IF NOT EXISTS items JSON;

COMMIT;
