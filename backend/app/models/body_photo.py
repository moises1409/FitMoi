from datetime import datetime, timezone

from .. import db


class BodyPhoto(db.Model):
    """Foto de progreso corporal, fechada, para comparar la evolución visual.

    A diferencia de las medidas, puede haber VARIAS por día (p. ej. frente,
    perfil y espalda del mismo día), así que no hay unique por fecha. El fichero
    se guarda en un subdirectorio propio de uploads (`body/`) para que la
    limpieza de fotos huérfanas de comida no las toque nunca.
    """

    __tablename__ = 'body_photos'

    id = db.Column(db.Integer, primary_key=True)
    taken_on = db.Column(db.Date, nullable=False, index=True)
    # frente | perfil | espalda | otra (orientativo; no obligatorio).
    pose = db.Column(db.String(12))
    filename = db.Column(db.String(255), nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'taken_on': self.taken_on.isoformat() if self.taken_on else None,
            'pose': self.pose,
            'filename': self.filename,
            'note': self.note,
            # URL relativa servida por el backend (bajo el candado, vía cookie).
            'url': f'/api/body/photos/{self.filename}',
        }
