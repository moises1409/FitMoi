from datetime import datetime, timezone

from .. import db


class UserProfile(db.Model):
    """Perfil del usuario que construye el entrenador conversacional.

    Lo que sirve para calcular (edad, sexo, peso, altura, días de entreno) va en
    columnas; lo que es una lista abierta o un matiz que no encaja en un campo
    se guarda en JSON o en texto libre. La conversación entera se conserva para
    poder retomarla y para que el modelo no repita preguntas.
    """

    __tablename__ = 'user_profiles'

    id = db.Column(db.Integer, primary_key=True)

    # ── Datos básicos (necesarios para estimar el gasto energético) ──
    age = db.Column(db.Integer)
    sex = db.Column(db.String(10))            # male | female | other
    weight_kg = db.Column(db.Float)
    height_cm = db.Column(db.Float)

    # ── Actividad ──
    training_days_per_week = db.Column(db.Integer)
    # Cada cuantos dias recordar que toca pesarse (mensual por defecto).
    weight_check_every_days = db.Column(db.Integer, default=30)
    # sedentary | light | moderate | active | very_active
    activity_level = db.Column(db.String(20))
    job_activity = db.Column(db.String(20))   # sedentary | standing | physical

    job = db.Column(db.Text)                  # descripción del trabajo
    location = db.Column(db.Text)             # dónde vive (clima, deporte al aire libre)

    # ── Listas abiertas ──
    sports = db.Column(db.JSON)               # ["carrera", "fuerza en gimnasio"]
    goals = db.Column(db.JSON)                # ["perder grasa", "ganar masa"]
    challenges = db.Column(db.JSON)           # [{"what": "...", "when": "..."}]
    conditions = db.Column(db.JSON)           # enfermedades / condiciones médicas
    injuries_current = db.Column(db.JSON)
    injuries_past = db.Column(db.JSON)
    diet_notes = db.Column(db.JSON)           # alergias, intolerancias, preferencias

    primary_goal = db.Column(db.Text)
    # lose | maintain | gain | recomp. Si esta vacio se deduce de los objetivos.
    goal_direction = db.Column(db.String(12))
    # Objetivos fijados a mano, que mandan sobre el calculo automatico.
    target_overrides = db.Column(db.JSON)
    # Todo lo que el usuario cuenta y no encaja en ningún campo.
    free_notes = db.Column(db.Text)

    # ── Conversación ──
    conversation = db.Column(db.JSON)         # [{"role": "...", "content": "..."}]
    completed = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    LIST_FIELDS = (
        'sports', 'goals', 'challenges', 'conditions',
        'injuries_current', 'injuries_past', 'diet_notes',
    )
    SCALAR_FIELDS = (
        'age', 'sex', 'weight_kg', 'height_cm', 'training_days_per_week',
        'activity_level', 'job_activity', 'job', 'location', 'primary_goal',
        'weight_check_every_days',
        'goal_direction', 'free_notes',
    )

    def to_dict(self) -> dict:
        data = {f: getattr(self, f) for f in self.SCALAR_FIELDS}
        data.update({f: getattr(self, f) or [] for f in self.LIST_FIELDS})
        data['id'] = self.id
        data['completed'] = self.completed
        data['conversation'] = self.conversation or []
        data['target_overrides'] = self.target_overrides or {}
        data['updated_at'] = self.updated_at.isoformat() if self.updated_at else None
        return data
