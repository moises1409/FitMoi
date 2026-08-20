"""Objetivos diarios de calorías y macronutrientes a partir del perfil.

La cadena es: peso/altura/edad/sexo -> metabolismo basal -> gasto diario según
actividad -> ajuste según el objetivo (perder, mantener, ganar) -> reparto de
macros. Cada paso se explica en `basis` para que el usuario vea de dónde sale
cada número y pueda discutirlo, en vez de recibir una cifra opaca.

Referencias usadas:
- Calorías: Mifflin-St Jeor, el estimador de basal con menos error medio.
- Proteína: 1,2-2,2 g/kg según objetivo y actividad; el extremo alto en déficit,
  que es cuando más masa magra se pierde. A partir de 60 años se sube el suelo
  por la menor respuesta anabólica.
- Grasa: mínimo 0,8 g/kg por función hormonal; por defecto el 27% de la energía.
- Fibra: 14 g por cada 1000 kcal.
- Saturadas: menos del 10% de la energía. Sal: menos de 5 g/día (OMS).
"""

GOAL_DIRECTIONS = ('lose', 'maintain', 'gain', 'recomp')

# Ajuste calórico sobre el gasto diario, por objetivo.
GOAL_ADJUST = {
    'lose': -0.15,
    'maintain': 0.0,
    'gain': 0.12,
    'recomp': -0.05,
}

GOAL_LABELS = {
    'lose': 'perder grasa',
    'maintain': 'mantenerte',
    'gain': 'ganar masa',
    'recomp': 'recomposición (perder grasa y ganar músculo)',
}

# Proteína en g por kg de peso corporal.
PROTEIN_PER_KG = {
    'lose': 2.0,
    'maintain': 1.6,
    'gain': 1.8,
    'recomp': 2.0,
}

FAT_ENERGY_SHARE = 0.27
FAT_MIN_PER_KG = 0.8
FIBER_PER_1000_KCAL = 14
SATURATED_MAX_SHARE = 0.10
SALT_MAX_G = 5.0

# Palabras del objetivo escrito con las que se deduce la dirección si no se ha
# fijado explícitamente.
_HINTS = (
    ('lose', ('perder', 'adelgaz', 'bajar', 'grasa', 'definir', 'defini')),
    ('gain', ('ganar', 'aumentar', 'masa', 'volumen', 'engordar', 'hipertrof')),
    ('maintain', ('mantener', 'mantenimiento', 'salud')),
)


def infer_direction(profile) -> str:
    """Deduce si busca perder, mantener o ganar a partir de lo que ha contado."""
    if profile.goal_direction in GOAL_DIRECTIONS:
        return profile.goal_direction

    texto = ' '.join(
        [profile.primary_goal or ''] + [str(g) for g in (profile.goals or [])]
    ).lower()

    encontrados = {
        direccion
        for direccion, palabras in _HINTS
        if any(p in texto for p in palabras)
    }

    # "perder grasa y definir" + "ganar músculo" a la vez es recomposición.
    if 'lose' in encontrados and 'gain' in encontrados:
        return 'recomp'
    for direccion in ('lose', 'gain', 'maintain'):
        if direccion in encontrados:
            return direccion
    return 'maintain'


def _protein_per_kg(profile, direction: str) -> float:
    per_kg = PROTEIN_PER_KG.get(direction, 1.6)

    # A partir de 60 la síntesis proteica responde peor: se sube el suelo.
    if (profile.age or 0) >= 60:
        per_kg = max(per_kg, 1.6)
    if (profile.age or 0) >= 70:
        per_kg = max(per_kg, 1.8)

    # Sin entrenamiento de fuerza no tiene sentido el extremo alto.
    dias = profile.training_days_per_week or 0
    if dias <= 1 and profile.activity_level in (None, 'sedentary', 'light'):
        per_kg = min(per_kg, 1.4)

    return round(per_kg, 2)


def compute(profile, energy) -> dict:
    """Objetivos del día. `energy` es lo que devuelve estimate_energy()."""
    if not energy:
        return None

    direction = infer_direction(profile)
    tdee = energy['tdee']
    adjust = GOAL_ADJUST.get(direction, 0.0)
    calories = round(tdee * (1 + adjust))

    peso = profile.weight_kg or 0
    per_kg = _protein_per_kg(profile, direction)
    protein_g = round(peso * per_kg) if peso else round(calories * 0.25 / 4)

    # Grasa: porcentaje de la energía, pero nunca por debajo del mínimo por kg.
    fats_g = round(calories * FAT_ENERGY_SHARE / 9)
    if peso:
        fats_g = max(fats_g, round(peso * FAT_MIN_PER_KG))

    # Los carbohidratos son el resto de la energía disponible.
    resto = calories - protein_g * 4 - fats_g * 9
    carbs_g = max(round(resto / 4), 0)

    basis = [
        f"Basal {energy['bmr']} kcal (Mifflin-St Jeor)",
        f"× {energy['activity_factor']} de actividad = {tdee} kcal de gasto diario",
    ]
    if adjust:
        signo = 'déficit' if adjust < 0 else 'superávit'
        basis.append(f"{signo} del {abs(round(adjust * 100))}% para {GOAL_LABELS[direction]}")
    else:
        basis.append(f"sin ajuste: objetivo de {GOAL_LABELS[direction]}")
    basis.append(f"Proteína a {per_kg} g por kg de peso")

    notes = []
    if direction == 'lose':
        notes.append(
            'La proteína va alta a propósito: en déficit es lo que protege la masa muscular.'
        )
    if direction == 'recomp':
        notes.append(
            'Recomposición: déficit pequeño y proteína alta. Es más lento, pero conserva músculo.'
        )
    if (profile.age or 0) >= 60:
        notes.append('Suelo de proteína elevado por edad: a partir de los 60 se aprovecha peor.')
    if profile.conditions:
        notes.append(
            'Tienes condiciones médicas registradas: contrasta estos objetivos con tu médico '
            'antes de seguirlos.'
        )

    targets = {
        'calories': calories,
        'proteins': protein_g,
        'carbs': carbs_g,
        'fats': fats_g,
        'fiber': round(calories / 1000 * FIBER_PER_1000_KCAL),
        'saturated_fat_max': round(calories * SATURATED_MAX_SHARE / 9),
        'salt_max': SALT_MAX_G,
        'protein_per_kg': per_kg,
        'goal_direction': direction,
        'goal_label': GOAL_LABELS[direction],
        'tdee': tdee,
        'basis': basis,
        'notes': notes,
        'overridden': [],
    }

    # Lo que el usuario haya fijado a mano manda sobre el cálculo.
    overrides = profile.target_overrides or {}
    for key in ('calories', 'proteins', 'carbs', 'fats', 'fiber'):
        value = overrides.get(key)
        if value in (None, ''):
            continue
        try:
            targets[key] = round(float(value))
            targets['overridden'].append(key)
        except (TypeError, ValueError):
            continue

    return targets
