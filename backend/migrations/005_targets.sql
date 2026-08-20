-- Dirección del objetivo y objetivos diarios fijados a mano.
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/005_targets.sql
BEGIN;
ALTER TABLE user_profiles
  ADD COLUMN IF NOT EXISTS goal_direction   VARCHAR(12),
  ADD COLUMN IF NOT EXISTS target_overrides JSON;
COMMIT;
