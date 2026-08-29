-- Integración con Withings: credenciales OAuth de la báscula y las columnas de
-- composición corporal en el histórico de peso.
--
-- create_all cubre la tabla nueva y las columnas en una BD nueva; este .sql las
-- añade sobre una BD ya desplegada (008+ se ejecutan una vez y se registran).
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/011_withings.sql

BEGIN;

-- Credenciales OAuth de Withings para el único usuario. Una sola fila: no hay
-- user_id. El refresh_token es un secreto de larga vida y NO se expone por la API.
CREATE TABLE IF NOT EXISTS withings_tokens (
    id               SERIAL PRIMARY KEY,
    withings_user_id VARCHAR(64),
    access_token     TEXT         NOT NULL,
    refresh_token    TEXT,
    scope            TEXT,
    expires_at       TIMESTAMPTZ  NOT NULL,
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_withings_tokens_user_id ON withings_tokens (withings_user_id);

-- Composición corporal de la báscula: solo la rellena una pesada de Withings;
-- una manual las deja en NULL. La grasa es %, el resto son masas en kg.
ALTER TABLE weight_entries
  ADD COLUMN IF NOT EXISTS fat_ratio      DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS fat_mass_kg    DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS muscle_mass_kg DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS bone_mass_kg   DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS hydration_kg   DOUBLE PRECISION;

-- La columna source pasa a admitir 'withings' (8 chars); antes era VARCHAR(10).
ALTER TABLE weight_entries
  ALTER COLUMN source TYPE VARCHAR(12);

COMMIT;
