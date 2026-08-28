-- Historial del chat con el entrenador-agente (charla libre, distinta de la
-- entrevista del perfil). App de usuario único: una sola fila con los mensajes
-- visibles de la conversación. Los turnos internos de herramientas no se
-- persisten. Idempotente.
--
--   docker exec -i fitmoi_db psql -U fitmoi -d fitmoi < backend/migrations/010_coach_conversation.sql

BEGIN;

CREATE TABLE IF NOT EXISTS coach_conversations (
    id         SERIAL PRIMARY KEY,
    messages   JSON,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMIT;
