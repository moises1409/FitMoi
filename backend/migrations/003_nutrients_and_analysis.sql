-- Grasas saturadas, sal y el análisis cualitativo del LLM (estimación de
-- porciones + valoración de lo más y lo menos sano).
--
-- Aplicar una sola vez:
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/003_nutrients_and_analysis.sql

BEGIN;

ALTER TABLE food_logs
  ADD COLUMN IF NOT EXISTS saturated_fat DOUBLE PRECISION DEFAULT 0,
  ADD COLUMN IF NOT EXISTS salt          DOUBLE PRECISION DEFAULT 0,
  ADD COLUMN IF NOT EXISTS analysis      JSON;

ALTER TABLE food_templates
  ADD COLUMN IF NOT EXISTS saturated_fat DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS salt          DOUBLE PRECISION NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS analysis      JSON;

-- Los registros anteriores no tenían estos valores: 0 es más honesto que NULL
-- para poder sumarlos en los totales del día.
UPDATE food_logs SET saturated_fat = 0 WHERE saturated_fat IS NULL;
UPDATE food_logs SET salt = 0 WHERE salt IS NULL;

COMMIT;
