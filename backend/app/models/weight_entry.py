from datetime import datetime, timezone

from .. import db


class WeightEntry(db.Model):
    """Una pesada. El peso deja de sobrescribirse para poder ver su evolución.

    Se guarda una entrada por día como mucho (`measured_on` es único): corregir
    la pesada de hoy actualiza la fila en vez de crear otra, que es lo que se
    espera cuando uno se equivoca al teclear.
    """

    __tablename__ = 'weight_entries'

    id = db.Column(db.Integer, primary_key=True)
    weight_kg = db.Column(db.Float, nullable=False)
    measured_on = db.Column(db.Date, nullable=False, unique=True, index=True)
    # manual | chat: de dónde salió el dato, para saber cuánto fiarse.
    source = db.Column(db.String(10), default='manual', nullable=False)
    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'weight_kg': self.weight_kg,
            'measured_on': self.measured_on.isoformat() if self.measured_on else None,
            'source': self.source,
            'note': self.note,
        }
