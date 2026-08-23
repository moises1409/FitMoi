from datetime import datetime, timezone

from .. import db


class WeeklyReview(db.Model):
    """Resumen semanal (lunes→domingo) de nutrición y actividad.

    Se genera de forma perezosa la primera vez que se consulta una semana ya
    cerrada (su domingo ha pasado) y se guarda: una fila por semana, con clave
    natural `(iso_year, iso_week)` para deduplicar. Regenerar corrige la misma
    fila en vez de crear otra, igual que las pesadas o el gasto del día.

    - `metrics` congela las cifras ya calculadas de la semana (medias, adherencia
      a objetivos, sesiones por familia, peso, gasto). Guardarlas permite que la
      comparativa de la semana siguiente sea exacta y barata sin recalcular ni
      volver a llamar al LLM sobre datos viejos.
    - `narrative` guarda lo que redacta el LLM sobre esas cifras: qué ha ido bien,
      qué mejorar, la comparativa con la semana anterior y las recomendaciones.
      El modelo nunca inventa números: solo redacta sobre `metrics`.
    """

    __tablename__ = 'weekly_reviews'

    id = db.Column(db.Integer, primary_key=True)

    # Semana ISO (lunes→domingo). La clave natural es (iso_year, iso_week); el
    # año ISO puede diferir del natural en el cambio de año, por eso se guarda.
    iso_year = db.Column(db.Integer, nullable=False)
    iso_week = db.Column(db.Integer, nullable=False)
    week_start = db.Column(db.Date, nullable=False, index=True)  # lunes
    week_end = db.Column(db.Date, nullable=False)                # domingo

    metrics = db.Column(db.JSON)
    narrative = db.Column(db.JSON)

    # Modelo que redactó la narrativa, para saber con qué se generó.
    model = db.Column(db.String(60))
    generated_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (
        db.UniqueConstraint('iso_year', 'iso_week', name='uq_weekly_reviews_isoweek'),
    )

    def to_dict(self) -> dict:
        generated = self.generated_at
        if generated is not None and generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)

        return {
            'iso_year': self.iso_year,
            'iso_week': self.iso_week,
            'week_start': self.week_start.isoformat() if self.week_start else None,
            'week_end': self.week_end.isoformat() if self.week_end else None,
            'metrics': self.metrics or {},
            'narrative': self.narrative or {},
            'model': self.model,
            'generated_at': generated.isoformat() if generated else None,
        }
