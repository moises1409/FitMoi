from datetime import datetime, timezone

from .. import db


class BodyMeasurement(db.Model):
    """Medidas corporales con cinta métrica, para seguir el progreso.

    Complementan el peso y la composición de la báscula con el contorno de
    distintas zonas (cintura, abdomen, pectoral, bíceps). Se registran con la
    frecuencia que uno quiera (p. ej. mensual): una fila por día como mucho
    (`measured_on` único), así repetir el mismo día corrige la toma anterior en
    vez de duplicarla, igual que el histórico de peso.
    """

    __tablename__ = 'body_measurements'

    id = db.Column(db.Integer, primary_key=True)
    measured_on = db.Column(db.Date, nullable=False, unique=True, index=True)

    # Contornos en cm; todos opcionales (uno puede tomar solo algunos ese día).
    waist_cm = db.Column(db.Float)         # cintura
    abdomen_cm = db.Column(db.Float)       # abdomen
    chest_cm = db.Column(db.Float)         # pectoral
    biceps_left_cm = db.Column(db.Float)   # bíceps izquierdo
    biceps_right_cm = db.Column(db.Float)  # bíceps derecho

    note = db.Column(db.Text)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Campos numéricos y su etiqueta legible (fuente única para vista, API y LLM).
    FIELDS = ('waist_cm', 'abdomen_cm', 'chest_cm', 'biceps_left_cm', 'biceps_right_cm')
    LABELS = {
        'waist_cm': 'Cintura',
        'abdomen_cm': 'Abdomen',
        'chest_cm': 'Pectoral',
        'biceps_left_cm': 'Bíceps izq.',
        'biceps_right_cm': 'Bíceps der.',
    }

    def has_any(self) -> bool:
        return any(getattr(self, f) is not None for f in self.FIELDS)

    def to_dict(self) -> dict:
        data = {f: getattr(self, f) for f in self.FIELDS}
        data['id'] = self.id
        data['measured_on'] = self.measured_on.isoformat() if self.measured_on else None
        data['note'] = self.note
        return data
