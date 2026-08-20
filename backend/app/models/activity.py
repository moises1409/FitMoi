from datetime import datetime, timezone

from .. import db


class Activity(db.Model):
    """Una sesión de actividad física, venga de donde venga.

    Manual y Whoop comparten tabla a propósito: las columnas están elegidas
    para encajar con lo que devuelve `/v2/activity/workout` (sport_name,
    kilojoule, start/end, strain, distance_meter, zone_durations), de modo que
    conectar la pulsera más adelante sea un mapeo y no una migración. Lo que
    solo trae Whoop vive en `metrics` para no llenar la tabla de columnas
    vacías en los registros manuales.
    """

    __tablename__ = 'activities'

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(10), nullable=False, default='manual')  # manual | whoop
    # UUID del workout en Whoop: evita duplicar al resincronizar.
    external_id = db.Column(db.String(64), unique=True, index=True)

    # Familia normalizada (strength, cardio, racket, mobility, other) con la que
    # se colorea el calendario; sport_name guarda el nombre real.
    activity_type = db.Column(db.String(20), nullable=False, default='other')
    sport_name = db.Column(db.String(120))

    started_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    duration_min = db.Column(db.Integer)
    calories = db.Column(db.Float)          # opcional en las manuales
    feeling = db.Column(db.Integer)         # 1-5, cómo fue la sesión
    notes = db.Column(db.Text)

    # strain, pulso medio/máximo, distancia, zonas... solo cuando hay pulsera.
    metrics = db.Column(db.JSON)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def to_dict(self) -> dict:
        started = self.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)

        return {
            'id': self.id,
            'source': self.source,
            'external_id': self.external_id,
            'activity_type': self.activity_type,
            'sport_name': self.sport_name,
            'started_at': started.isoformat() if started else None,
            'duration_min': self.duration_min,
            'calories': self.calories,
            'feeling': self.feeling,
            'notes': self.notes,
            'metrics': self.metrics or {},
        }
