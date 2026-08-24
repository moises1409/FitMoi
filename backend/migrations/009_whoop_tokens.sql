-- Credenciales OAuth de Whoop para el único usuario de la app. Una sola fila:
-- no hay user_id. El refresh_token es un secreto de larga vida y NO debe
-- exponerse por la API. create_all cubre esta tabla en una BD nueva; este .sql
-- la añade sobre una BD ya desplegada (008+ se ejecutan una vez y se registran).
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/009_whoop_tokens.sql

BEGIN;

CREATE TABLE IF NOT EXISTS whoop_tokens (
    id            SERIAL PRIMARY KEY,
    whoop_user_id VARCHAR(64),
    access_token  TEXT         NOT NULL,
    refresh_token TEXT,
    scope         TEXT,
    expires_at    TIMESTAMPTZ  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_whoop_tokens_user_id ON whoop_tokens (whoop_user_id);

COMMIT;
