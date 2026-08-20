from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import current_app

from .. import db


class FoodTemplate(db.Model):
    """Entrada reutilizable de la biblioteca: un plato o un alimento suelto.

    Los macros se guardan para una porción de referencia (1x). Al registrar una
    comida se multiplican por la porción elegida y se copian al FoodLog; editar
    la plantilla reescribe además esos registros (library_service.propagate_to_logs).
    """

    __tablename__ = 'food_templates'

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(10), nullable=False, default='dish')  # dish | food
    name = db.Column(db.String(200), nullable=False)
    # Nombre normalizado (sin acentos, minúsculas): identidad para deduplicar.
    normalized_name = db.Column(db.String(200), nullable=False, unique=True, index=True)
    quantity_label = db.Column(db.String(80), default='')

    calories = db.Column(db.Float, default=0, nullable=False)
    proteins = db.Column(db.Float, default=0, nullable=False)
    carbs = db.Column(db.Float, default=0, nullable=False)
    fats = db.Column(db.Float, default=0, nullable=False)
    fiber = db.Column(db.Float, default=0, nullable=False)
    saturated_fat = db.Column(db.Float, default=0, nullable=False)
    salt = db.Column(db.Float, default=0, nullable=False)

    # Desglose de alimentos cuando kind == 'dish'
    components = db.Column(db.JSON)
    # Estimación de porciones y valoración nutricional del LLM.
    analysis = db.Column(db.JSON)
    photo_path = db.Column(db.String(255))
    source = db.Column(db.String(10), default='ai', nullable=False)  # ai | manual

    times_used = db.Column(db.Integer, default=0, nullable=False)
    # {"breakfast": 3, "lunch": 9, ...} -> alimenta el ranking por franja horaria
    meal_type_counts = db.Column(db.JSON, default=dict)
    last_used_at = db.Column(db.DateTime(timezone=True), index=True)

    archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def usual_meal_type(self) -> str | None:
        """Franja en la que más veces se ha tomado."""
        counts = self.meal_type_counts or {}
        return max(counts, key=counts.get) if counts else None

    def usual_time(self) -> str | None:
        """Hora ('HH:MM', local) de la última vez que se registró.

        Sirve de valor por defecto al volver a añadirlo: si siempre desayunas
        lo mismo a las 8:30, no tiene sentido proponer la hora actual.
        """
        last_used = self.last_used_at
        if last_used is None:
            return None
        if last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)

        try:
            tz = ZoneInfo(current_app.config['APP_TIMEZONE'])
        except (ZoneInfoNotFoundError, ValueError, RuntimeError, KeyError):
            tz = timezone.utc
        return last_used.astimezone(tz).strftime('%H:%M')

    def to_dict(self) -> dict:
        last_used = self.last_used_at
        if last_used is not None and last_used.tzinfo is None:
            last_used = last_used.replace(tzinfo=timezone.utc)

        return {
            'usual_meal_type': self.usual_meal_type(),
            'usual_time': self.usual_time(),
            'id': self.id,
            'kind': self.kind,
            'name': self.name,
            'quantity_label': self.quantity_label or '',
            'calories': self.calories,
            'proteins': self.proteins,
            'carbs': self.carbs,
            'fats': self.fats,
            'fiber': self.fiber,
            'saturated_fat': self.saturated_fat,
            'salt': self.salt,
            'analysis': self.analysis or {},
            'components': self.components or [],
            'photo_url': f'/api/food/uploads/{self.photo_path}' if self.photo_path else None,
            'source': self.source,
            'times_used': self.times_used,
            'last_used_at': last_used.isoformat() if last_used else None,
        }
