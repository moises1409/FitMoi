-- Desdobla el bíceps en izquierdo y derecho en las medidas corporales.
--
-- create_all cubre estas columnas en una BD nueva (el modelo ya las define);
-- este .sql las añade sobre una BD ya desplegada y migra el valor antiguo de
-- `biceps_cm` a `biceps_right_cm`. La columna vieja se conserva (sin usar) para
-- no perder datos; el modelo simplemente ya no la mapea.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/012_body_biceps.sql

BEGIN;

ALTER TABLE body_measurements
  ADD COLUMN IF NOT EXISTS biceps_left_cm  DOUBLE PRECISION,
  ADD COLUMN IF NOT EXISTS biceps_right_cm DOUBLE PRECISION;

-- Migra el bíceps único registrado hasta ahora al lado derecho (por convención),
-- solo si la columna vieja existe y el destino está vacío. Idempotente.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'body_measurements' AND column_name = 'biceps_cm'
  ) THEN
    UPDATE body_measurements
       SET biceps_right_cm = biceps_cm
     WHERE biceps_cm IS NOT NULL AND biceps_right_cm IS NULL;
  END IF;
END $$;

COMMIT;
