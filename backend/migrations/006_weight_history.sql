-- Histórico de peso: una entrada por pesada en lugar de un único valor
-- que se sobrescribe. Permite ver la evolución mes a mes.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/006_weight_history.sql

BEGIN;

CREATE TABLE IF NOT EXISTS weight_entries (
    id          SERIAL PRIMARY KEY,
    weight_kg   DOUBLE PRECISION NOT NULL,
    measured_on DATE        NOT NULL UNIQUE,
    source      VARCHAR(10) NOT NULL DEFAULT 'manual',
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_weight_entries_measured_on ON weight_entries (measured_on);

-- Cada cuántos días recordar que toca pesarse.
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS weight_check_every_days INTEGER DEFAULT 30;

-- El peso que ya había registrado se convierte en la primera pesada del
-- histórico, para no empezar con la gráfica vacía.
INSERT INTO weight_entries (weight_kg, measured_on, source, note)
SELECT weight_kg, CURRENT_DATE, 'manual', 'Primera pesada registrada en el perfil'
FROM user_profiles
WHERE weight_kg IS NOT NULL
ON CONFLICT (measured_on) DO NOTHING;

COMMIT;
