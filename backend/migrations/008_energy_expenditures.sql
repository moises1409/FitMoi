-- Calorías gastadas por día natural: el gasto energético total del día, no el
-- de una sesión suelta. Una entrada por día como mucho (manual hoy, Whoop en
-- el futuro). Reintroducir el mismo día corrige la fila en vez de duplicarla.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/008_energy_expenditures.sql

BEGIN;

CREATE TABLE IF NOT EXISTS energy_expenditures (
    id          SERIAL PRIMARY KEY,
    calories    DOUBLE PRECISION NOT NULL,
    measured_on DATE        NOT NULL UNIQUE,
    source      VARCHAR(10) NOT NULL DEFAULT 'manual',
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_energy_expenditures_measured_on ON energy_expenditures (measured_on);

COMMIT;
