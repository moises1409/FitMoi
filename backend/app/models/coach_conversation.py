from datetime import datetime, timezone

from .. import db


class CoachConversation(db.Model):
    """Historial del chat con el entrenador-agente.

    A diferencia de `user_profiles.conversation` (la ENTREVISTA que construye el
    perfil), esta es la charla libre con el entrenador: el usuario le pregunta lo
    que quiere y el modelo responde con TODOS sus datos como contexto (nutrición,
    actividad, gasto, peso, objetivos). App de usuario único: una sola fila.

    Solo se guardan los mensajes visibles de la charla (`user`/`assistant`); los
    turnos internos de uso de herramientas NO se persisten, se resuelven en cada
    petición y el resultado ya queda reflejado en la respuesta del asistente.
    """

    __tablename__ = 'coach_conversations'

    id = db.Column(db.Integer, primary_key=True)
    messages = db.Column(db.JSON)  # [{"role": "user"|"assistant", "content": "..."}]

    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'messages': self.messages or [],
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
