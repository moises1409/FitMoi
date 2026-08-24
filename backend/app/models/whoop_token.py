from datetime import datetime, timezone

from .. import db


class WhoopToken(db.Model):
    """Credenciales OAuth de Whoop para el único usuario de la app.

    App de usuario único: hay como mucho UNA fila (no hay `user_id`). Guarda el
    par access/refresh y cuándo caduca el access, para poder refrescarlo sin
    volver a pedir consentimiento. El `whoop_user_id` y el `scope` se guardan
    informativos (validar webhooks, saber qué permisos concedió).

    El refresh token es un secreto de larga vida: esta tabla no debe exponerse
    nunca por la API. Solo la usa `whoop_service`.
    """

    __tablename__ = 'whoop_tokens'

    id = db.Column(db.Integer, primary_key=True)
    whoop_user_id = db.Column(db.String(64), index=True)
    access_token = db.Column(db.Text, nullable=False)
    refresh_token = db.Column(db.Text)
    scope = db.Column(db.Text)
    # Momento (UTC) en que caduca el access_token; antes de eso se refresca.
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def is_expired(self, skew_seconds: int = 60) -> bool:
        """True si el access_token ya caducó (o está a punto, con margen)."""
        expira = self.expires_at
        if expira is None:
            return True
        if expira.tzinfo is None:
            expira = expira.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc).timestamp() >= expira.timestamp() - skew_seconds
