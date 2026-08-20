-- Convierte created_at a timestamptz.
--
-- El codigo anterior guardaba datetime.now(timezone.utc) en una columna
-- "timestamp without time zone", asi que los valores existentes son hora UTC
-- sin offset: el USING los reinterpreta como UTC sin desplazarlos.
--
-- Aplicar una sola vez:
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/001_created_at_timestamptz.sql

BEGIN;

UPDATE food_logs SET created_at = NOW() AT TIME ZONE 'UTC' WHERE created_at IS NULL;

ALTER TABLE food_logs
  ALTER COLUMN created_at TYPE timestamptz USING created_at AT TIME ZONE 'UTC';

ALTER TABLE food_logs
  ALTER COLUMN created_at SET NOT NULL;

CREATE INDEX IF NOT EXISTS ix_food_logs_created_at ON food_logs (created_at);

COMMIT;
