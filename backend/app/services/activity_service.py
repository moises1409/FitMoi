"""Actividad física: taxonomía, consultas y normalización.

Whoop maneja más de cien nombres de deporte, así que el calendario no puede
pintar un color por deporte: por encima de siete u ocho tonos dejan de
distinguirse, y más aún con daltonismo. Todo se normaliza a cinco familias con
color fijo, y el nombre real se conserva en `sport_name` para el detalle.

Los colores están validados (banda de luminosidad, croma, separación bajo
daltonismo y contraste) sobre las superficies clara y oscura de la app.
"""

import unicodedata

from sqlalchemy import func

from .. import db
from ..models.activity import Activity

# Orden fijo de las familias: nunca se rota ni se genera un color nuevo.
FAMILIES = [
    {'key': 'strength', 'label': 'Fuerza', 'color': '#6C4DE0', 'icon': 'fitness_center'},
    {'key': 'racket', 'label': 'Raqueta y equipo', 'color': '#D97706', 'icon': 'sports_tennis'},
    {'key': 'cardio', 'label': 'Cardio', 'color': '#0891B2', 'icon': 'directions_run'},
    {'key': 'mobility', 'label': 'Movilidad', 'color': '#DB2777', 'icon': 'self_improvement'},
    {'key': 'other', 'label': 'Otro', 'color': '#4D7C0F', 'icon': 'sports'},
]
FAMILY_KEYS = {f['key'] for f in FAMILIES}

# Palabras que asignan un deporte a su familia. Cubre lo que escribe el usuario
# en español y los `sport_name` que devuelve Whoop en inglés.
_KEYWORDS = [
    ('strength', (
        'fuerza', 'pesas', 'gimnasio', 'gym', 'calistenia', 'calisthenics',
        'circuit', 'crossfit', 'functional', 'weightlifting', 'powerlifting',
        'strength', 'musculacion', 'body weight', 'peso corporal',
    )),
    ('racket', (
        'padel', 'paddle', 'tenis', 'tennis', 'squash', 'badminton', 'pickleball',
        'futbol', 'soccer', 'football', 'baloncesto', 'basketball', 'voleibol',
        'volleyball', 'hockey', 'rugby', 'balonmano',
    )),
    ('cardio', (
        'correr', 'carrera', 'running', 'run', 'trail', 'maraton', 'bici',
        'ciclismo', 'cycling', 'bike', 'spinning', 'nadar', 'natacion',
        'swim', 'remo', 'rowing', 'eliptica', 'elliptical', 'hiit',
        'cardio', 'escalada', 'climbing', 'esqui', 'ski', 'boxeo', 'boxing',
    )),
    ('mobility', (
        'yoga', 'pilates', 'estiramiento', 'stretch', 'movilidad', 'mobility',
        'caminar', 'andar', 'walking', 'walk', 'senderismo', 'hiking',
        'meditacion', 'meditation', 'recovery', 'descanso activo',
    )),
]


def _normalize(text: str) -> str:
    text = unicodedata.normalize('NFKD', (text or '').strip().lower())
    return ''.join(c for c in text if not unicodedata.combining(c))


def classify(sport_name: str) -> str:
    """Deduce la familia a partir del nombre del deporte."""
    texto = _normalize(sport_name)
    if not texto:
        return 'other'
    for familia, palabras in _KEYWORDS:
        if any(p in texto for p in palabras):
            return familia
    return 'other'


def family_of(activity_type: str, sport_name: str) -> str:
    """Respeta la familia elegida a mano; si no es válida, la deduce."""
    if activity_type in FAMILY_KEYS:
        return activity_type
    return classify(sport_name)


def for_day(day_start, day_end) -> list:
    return (
        Activity.query
        .filter(Activity.started_at >= day_start, Activity.started_at < day_end)
        .order_by(Activity.started_at.asc())
        .all()
    )


def totals(activities: list) -> dict:
    """Resumen del día: cuánto se ha movido y cuánto ha costado."""
    minutos = sum(a.duration_min or 0 for a in activities)
    calorias = sum(a.calories or 0 for a in activities)
    return {
        'sessions': len(activities),
        'minutes': minutos,
        # Informativo, NO se resta del balance: el objetivo diario ya incluye
        # un factor de actividad y restarlas otra vez las contaría dos veces.
        'calories': round(calorias, 1),
    }


def families_by_day(window_start, window_end, tz_name: str) -> dict:
    """Familias con actividad en cada día natural, para los puntos del mes.

    Se agrupa en SQL convirtiendo a la zona del usuario, igual que el resumen
    de comidas: traerse todas las sesiones para agruparlas en Python no escala.
    """
    dia = func.date(func.timezone(tz_name, Activity.started_at))
    filas = (
        db.session.query(dia.label('day'), Activity.activity_type, func.count().label('n'))
        .filter(Activity.started_at >= window_start, Activity.started_at < window_end)
        .group_by(dia, Activity.activity_type)
        .all()
    )

    salida: dict = {}
    for fila in filas:
        clave = fila.day.isoformat()
        salida.setdefault(clave, []).append({
            'family': fila.activity_type,
            'count': fila.n,
        })
    return salida
