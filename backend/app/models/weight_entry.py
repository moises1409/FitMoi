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
    # manual | chat | withings: de dónde salió el dato, para saber cuánto fiarse.
    source = db.Column(db.String(12), default='manual', nullable=False)
    note = db.Column(db.Text)

    # ── Composición corporal (báscula Withings) ──
    # Solo la báscula inteligente los rellena; una pesada manual los deja en NULL.
    # Withings da la grasa como % y el resto de masas en kg; el % de músculo/hueso/
    # agua respecto al peso lo deriva la vista (masa_kg / peso * 100), como hace la
    # propia app de Withings. Se guarda el dato crudo tal como llega, sin escalar.
    fat_ratio = db.Column(db.Float)        # % de masa grasa (tipo 6)
    fat_mass_kg = db.Column(db.Float)      # masa grasa en kg (tipo 8)
    muscle_mass_kg = db.Column(db.Float)   # masa muscular en kg (tipo 76)
    bone_mass_kg = db.Column(db.Float)     # masa ósea en kg (tipo 88)
    hydration_kg = db.Column(db.Float)     # agua corporal en kg (tipo 77)

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def _ratio(self, mass_kg) -> float | None:
        """Porcentaje de una masa respecto al peso total, redondeado a 1 decimal."""
        if mass_kg is None or not self.weight_kg:
            return None
        return round(mass_kg / self.weight_kg * 100, 1)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'weight_kg': self.weight_kg,
            'measured_on': self.measured_on.isoformat() if self.measured_on else None,
            'source': self.source,
            'note': self.note,
            # Composición corporal: crudo + porcentajes derivados para la vista.
            'fat_ratio': self.fat_ratio,
            'fat_mass_kg': self.fat_mass_kg,
            'muscle_mass_kg': self.muscle_mass_kg,
            'bone_mass_kg': self.bone_mass_kg,
            'hydration_kg': self.hydration_kg,
            'muscle_ratio': self._ratio(self.muscle_mass_kg),
            'bone_ratio': self._ratio(self.bone_mass_kg),
            'water_ratio': self._ratio(self.hydration_kg),
            'has_composition': any(
                v is not None for v in (
                    self.fat_ratio, self.fat_mass_kg, self.muscle_mass_kg,
                    self.bone_mass_kg, self.hydration_kg,
                )
            ),
        }
