"""Entrenador personal conversacional que construye el perfil del usuario.

El modelo hace de entrevistador: pregunta, interpreta respuestas en lenguaje
natural y devuelve los campos que ha podido estructurar. Lo que no encaja en
ningún campo se acumula en `free_notes` en vez de perderse.
"""

import json

import anthropic
from flask import current_app

from .. import db
from ..models.user_profile import UserProfile
from . import weight_service
from . import profile_tool
from .claude_service import AnalysisError

# Orden en el que conviene preguntar: primero lo que permite calcular, luego
# lo que personaliza, y al final lo delicado (lesiones, enfermedades).
TOPICS = [
    ('age', 'edad'),
    ('sex', 'sexo'),
    ('weight_kg', 'peso'),
    ('height_cm', 'altura'),
    ('training_days_per_week', 'días de entrenamiento por semana'),
    ('sports', 'qué deportes practica'),
    ('job', 'en qué trabaja y si es sedentario'),
    ('location', 'dónde vive'),
    ('goals', 'sus objetivos'),
    ('challenges', 'retos o competiciones'),
    ('conditions', 'enfermedades o condiciones médicas'),
    ('injuries_current', 'dolencias o lesiones actuales'),
    ('injuries_past', 'lesiones pasadas'),
    ('diet_notes', 'alergias, intolerancias o preferencias alimentarias'),
]

SYSTEM = """Eres el entrenador personal de esta persona y estás haciendo la primera
entrevista para construir su perfil. Con él personalizarás sus rutinas y sus
recomendaciones de nutrición y salud.

Cómo hablas:
- Cercano y profesional, de tú, en español. Nada de tecnicismos innecesarios.
- UNA pregunta por turno, dos como mucho si son de lo mismo (peso y altura).
- Reacciona brevemente a lo que te acaba de contar antes de preguntar lo siguiente.
- Nunca preguntes algo que ya sabes. Mira el perfil actual antes de hablar.
- Si responde con vaguedad, acepta lo que te dé y sigue; puedes afinar más tarde.
- Si dice que prefiere no contestar, respétalo y pasa al siguiente tema.
- Con lesiones y enfermedades sé especialmente cuidadoso: explica que preguntas
  para no recomendarle nada que le perjudique.
- Cuando ya tengas lo esencial, dilo y ofrece cerrar, sin alargarlo.

Cómo interpretas:
- Traduce lenguaje natural a datos: "voy al gym 3 veces" -> training_days_per_week: 3.
- "94 kilos", "1,82" o "mido 182" son peso y altura aunque no lo diga con unidades.
- activity_level lo deduces tú combinando trabajo y entrenamiento:
  sedentary, light, moderate, active, very_active.
- job_activity: sedentary (oficina), standing (de pie), physical (esfuerzo).
- Todo lo que cuente y no encaje en un campo concreto (contexto, matices,
  historias relevantes) lo añades a free_notes SIN borrar lo que ya había.
"""


GREETING = (
    '¡Hola! Voy a ser tu entrenador y quiero conocerte antes de recomendarte nada. '
    'Te haré unas preguntas rápidas: cuanto mejor te conozca, más se ajustarán a ti '
    'las rutinas y la alimentación. Puedes saltarte lo que no quieras contestar.\n\n'
    '¿Empezamos por lo básico? ¿Qué edad tienes?'
)


def get_or_create() -> UserProfile:
    profile = UserProfile.query.first()
    if profile is None:
        profile = UserProfile(conversation=[{'role': 'assistant', 'content': GREETING}])
        db.session.add(profile)
        db.session.commit()
    return profile


def missing_topics(profile: UserProfile) -> list:
    """Campos sin valor, en el orden en que conviene preguntarlos."""
    out = []
    for field, label in TOPICS:
        value = getattr(profile, field, None)
        if value is None or value == '' or value == []:
            out.append(label)
    return out


def completeness(profile: UserProfile) -> int:
    total = len(TOPICS)
    return round((total - len(missing_topics(profile))) / total * 100)


def estimate_energy(profile: UserProfile):
    """Metabolismo basal (Mifflin-St Jeor) y gasto diario estimado.

    Es un punto de partida, no un dogma: sirve para proponer un objetivo de
    calorías en vez del 2000 fijo que hay ahora.
    """
    if not (profile.weight_kg and profile.height_cm and profile.age and profile.sex):
        return None

    base = 10 * profile.weight_kg + 6.25 * profile.height_cm - 5 * profile.age
    bmr = base + (5 if profile.sex == 'male' else -161)

    factors = {
        'sedentary': 1.2,
        'light': 1.375,
        'moderate': 1.55,
        'active': 1.725,
        'very_active': 1.9,
    }
    factor = factors.get(profile.activity_level or '')
    if factor is None:
        days = profile.training_days_per_week or 0
        factor = 1.2 if days <= 0 else 1.375 if days <= 2 else 1.55 if days <= 4 else 1.725

    tdee = bmr * factor
    return {
        'bmr': round(bmr),
        'tdee': round(tdee),
        'activity_factor': factor,
        # Déficit/superávit del 15%: el rango prudente que sostiene la evidencia.
        'target_lose': round(tdee * 0.85),
        'target_gain': round(tdee * 1.15),
    }


def apply_updates(profile: UserProfile, updates) -> list:
    """Vuelca los campos aprendidos. Devuelve los que han cambiado."""
    if not isinstance(updates, dict):
        return []

    changed = []
    for field, value in updates.items():
        if field not in UserProfile.SCALAR_FIELDS and field not in UserProfile.LIST_FIELDS:
            continue
        if value is None or value == '':
            continue

        if field in UserProfile.LIST_FIELDS:
            if not isinstance(value, list):
                value = [value]
            value = [v for v in value if v not in ('', None)]
            if not value:
                continue
        elif field in ('age', 'training_days_per_week'):
            try:
                value = int(float(value))
            except (TypeError, ValueError):
                continue
        elif field == 'weight_kg':
            # El peso va al historico; _sync_current deja el perfil al dia.
            try:
                weight_service.record(profile, value, source='chat')
            except ValueError:
                continue
            changed.append(field)
            continue
        elif field == 'height_cm':
            try:
                value = round(float(value), 1)
            except (TypeError, ValueError):
                continue
        elif field == 'free_notes':
            # SUSTITUYE, no acumula: el modelo reenvia el texto completo y
            # actualizado en cada turno (igual que con las listas). Concatenar
            # aqui producia el mismo parrafo repetido una y otra vez.
            value = str(value).strip()
            if not value:
                continue
        else:
            value = str(value).strip()

        if getattr(profile, field) != value:
            setattr(profile, field, value)
            changed.append(field)

    return changed


def _profile_context(profile: UserProfile) -> str:
    known = {}
    for field in tuple(UserProfile.SCALAR_FIELDS) + tuple(UserProfile.LIST_FIELDS):
        value = getattr(profile, field)
        if value not in (None, '', []):
            known[field] = value

    missing = missing_topics(profile)
    resumen = json.dumps(known, ensure_ascii=False, indent=2) if known else '(vacío)'
    pendiente = ', '.join(missing) if missing else 'nada, ya está completo'
    return (
        'PERFIL ACTUAL (no vuelvas a preguntar esto):\n'
        + resumen
        + '\n\nAÚN FALTA POR SABER: '
        + pendiente
        + '\n'
    )


def _system_prompt(profile: UserProfile) -> str:
    """Instrucciones del entrenador mas el estado actual del perfil."""
    separador = chr(10) * 2
    return SYSTEM + separador + _profile_context(profile)


def chat(profile: UserProfile, message: str) -> dict:
    """Un turno de la entrevista. Devuelve la respuesta y aplica lo aprendido."""
    client = anthropic.Anthropic(api_key=current_app.config['ANTHROPIC_API_KEY'])

    history = list(profile.conversation or [])
    history.append({'role': 'user', 'content': message})

    # Solo los últimos turnos: el contexto del perfil ya resume lo anterior.
    recent = history[-20:]

    response = client.messages.create(
        model=current_app.config['ANTHROPIC_MODEL'],
        max_tokens=1024,
        system=_system_prompt(profile),
        tools=[profile_tool.TOOL],
        # Forzada: el modelo debe responder SIEMPRE a traves de la herramienta.
        tool_choice={'type': 'tool', 'name': profile_tool.TOOL_NAME},
        messages=[{'role': m['role'], 'content': m['content']} for m in recent],
    )

    if response.stop_reason == 'refusal':
        raise AnalysisError('El modelo no pudo responder a este mensaje.')

    block = next(
        (b for b in response.content if b.type == 'tool_use' and b.name == profile_tool.TOOL_NAME),
        None,
    )
    if block is None:
        raise AnalysisError('El modelo no uso la herramienta de respuesta.')

    data = block.input if isinstance(block.input, dict) else {}
    reply = str(data.get('reply', '')).strip()
    if not reply:
        raise AnalysisError('El modelo no devolvio respuesta para el usuario.')

    changed = apply_updates(profile, data.get('updates'))
    if data.get('complete') is True:
        profile.completed = True

    history.append({'role': 'assistant', 'content': reply})
    profile.conversation = history[-60:]

    db.session.commit()
    return {'reply': reply, 'changed': changed}


def reset_conversation(profile: UserProfile) -> None:
    """Reinicia la charla conservando lo que ya se sabe del usuario."""
    profile.conversation = [{'role': 'assistant', 'content': GREETING}]
    profile.completed = False
    db.session.commit()
