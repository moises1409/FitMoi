from datetime import datetime, timezone
from .. import db


class FoodLog(db.Model):
    __tablename__ = 'food_logs'

    id = db.Column(db.Integer, primary_key=True)
    meal_type = db.Column(db.String(20), nullable=False, default='snack')
    photo_path = db.Column(db.String(255))
    description = db.Column(db.Text)
    foods_detected = db.Column(db.JSON)
    total_calories = db.Column(db.Float, default=0)
    proteins = db.Column(db.Float, default=0)
    carbs = db.Column(db.Float, default=0)
    fats = db.Column(db.Float, default=0)
    fiber = db.Column(db.Float, default=0)
    saturated_fat = db.Column(db.Float, default=0)
    salt = db.Column(db.Float, default=0)
    confidence = db.Column(db.String(10))
    notes = db.Column(db.Text)
    # Estimación de porciones y valoración nutricional que devolvió el LLM.
    analysis = db.Column(db.JSON)
    # Copia de los elementos que componen la comida, con sus macros ya escalados.
    # template_id enlaza con la plantilla para poder propagar sus ediciones.
    items = db.Column(db.JSON)
    # timezone=True -> timestamptz. Sin esto el offset se pierde al guardar y
    # el frontend interpreta la hora UTC como hora local.
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    def to_dict(self):
        created = self.created_at
        if created is not None and created.tzinfo is None:
            # Filas creadas antes de migrar la columna a timestamptz.
            created = created.replace(tzinfo=timezone.utc)

        return {
            'id': self.id,
            'meal_type': self.meal_type,
            'photo_url': f'/api/food/uploads/{self.photo_path}' if self.photo_path else None,
            'description': self.description,
            'foods_detected': self.foods_detected or [],
            'items': self.items or [],
            'total_calories': self.total_calories,
            'proteins': self.proteins,
            'carbs': self.carbs,
            'fats': self.fats,
            'fiber': self.fiber,
            'saturated_fat': self.saturated_fat,
            'salt': self.salt,
            'analysis': self.analysis or {},
            'confidence': self.confidence,
            'notes': self.notes,
            'created_at': created.isoformat() if created else None,
        }
