from datetime import datetime, timezone

from .. import db


class EnergyExpenditure(db.Model):
    """Calorías gastadas en un día natural: el gasto energético total.

    Es un valor único por día, no por sesión. Las calorías de cada `Activity`
    son informativas (una sesión suelta); esto es el gasto del día entero, que
    es lo que se compara con lo consumido. Hoy se introduce a mano y en el
    futuro lo rellenará Whoop (que mide el gasto real del día): por eso lleva
    `source` y una entrada por día como mucho (`measured_on` es único), igual
    que `weight_entries`. Reintroducir el mismo día corrige la fila en vez de
    duplicarla, que es lo que se espera al reescribir un dato.
    """

    __tablename__ = 'energy_expenditures'

    id = db.Column(db.Integer, primary_key=True)
    calories = db.Column(db.Float, nullable=False)
    measured_on = db.Column(db.Date, nullable=False, unique=True, index=True)
    # manual | whoop: de dónde salió el dato, para saber cuánto fiarse y para
    # que la sincronización de la pulsera no pise una corrección hecha a mano
    # sin querer.
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
            'calories': self.calories,
            'measured_on': self.measured_on.isoformat() if self.measured_on else None,
            'source': self.source,
            'note': self.note,
        }
