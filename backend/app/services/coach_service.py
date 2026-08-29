"""Entrenador-agente: chat libre con TODOS los datos del usuario como contexto.

A diferencia de `profile_service` (la ENTREVISTA que rellena el perfil), aquí el
usuario pregunta lo que quiere ("¿voy bien de proteína esta semana?", "¿qué
entreno me conviene mañana?", "¿por qué no bajo de peso?") y el entrenador
responde apoyándose en su nutrición, actividad, gasto, peso y objetivos.

Cómo se le dan los datos:
- **Contexto base en el prompt de sistema**: perfil + objetivos + peso + un
  resumen compacto de las últimas semanas + el detalle de la semana en curso.
  Es lo que casi siempre hace falta y va en cada turno.
- **Herramientas a demanda** (`coach_tool`): para el detalle fino que no cabe en
  el contexto base (qué comió un día concreto, nutrición o actividades de un
  rango). El modelo las llama solo si la pregunta lo pide; el bucle de `chat`
  las ejecuta y le devuelve el resultado hasta que produce la respuesta final.

Esto lo hace un agente de verdad (razona sobre datos que él mismo pide) sin
inflar cada petición con toda la base de datos.
"""

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from flask import current_app

from .. import db
from ..models.activity import Activity
from ..models.coach_conversation import CoachConversation
from ..models.energy_expenditure import EnergyExpenditure
from ..models.food_log import FoodLog
from . import (activity_service, coach_tool, profile_service, targets_service,
               weekly_review_service, weight_service)
from .claude_service import AnalysisError

# Cuántas semanas cerradas resumir en el contexto base. Más allá, que el agente
# baje al dato con las herramientas: no conviene inflar cada turno.
CONTEXT_WEEKS = 6
# Tope de vueltas del bucle de herramientas: evita que un modelo que insiste en
# pedir datos se quede en bucle. En la práctica basta con 2-3.
MAX_TOOL_ITERATIONS = 6
# Turnos visibles que se reenvían como historial. El resto ya está resumido en
# el contexto base, así que no hace falta arrastrarlo entero.
HISTORY_TURNS = 24
# Topes defensivos para las herramientas de rango: una pregunta sobre "el último
# año" no debe devolver miles de filas de golpe.
MAX_RANGE_DAYS = 92
MAX_ACTIVITIES = 120

MAX_MESSAGE = 2000


SYSTEM = """Eres el entrenador personal y nutricionista de esta persona dentro de
su app FitMoi. Te conoce y confía en ti: le has visto la comida, los
entrenamientos, el peso, la composición corporal y el gasto de las últimas semanas.

Cómo hablas:
- En español, de tú, cercano y directo. Nada de tecnicismos innecesarios ni paja.
- Respuestas útiles y al grano; usa listas o pasos solo cuando ayuden.
- Motivador pero honesto: si algo va flojo, dilo, pero con una salida concreta.

Cómo respondes:
- Apóyate SIEMPRE en sus datos. Ancla lo que digas a cifras reales (kcal, gramos
  de proteína, sesiones, minutos, peso, composición corporal, gasto) en vez de
  generalidades.
- Tienes en el contexto su perfil, sus objetivos del día, su peso y su composición
  corporal (grasa, músculo, hueso y agua, cuando usa la báscula Withings, con la
  evolución en las últimas pesadas) y un resumen de las últimas semanas con el
  detalle de la semana en curso. Si necesitas el detalle de un día concreto o de
  un rango que no está ahí, usa las herramientas para consultarlo antes de
  responder. No te inventes números que no tengas. Si te preguntan por la
  composición y no hay datos aún, dile que se pese con la báscula conectada.
- Ten en cuenta su objetivo (perder grasa, mantener, ganar, recomposición) y sus
  lesiones o condiciones médicas: nunca recomiendes nada que las ignore.
- Si te falta un dato para responder bien, pídeselo o dile cómo registrarlo.
- No des consejo médico: ante señales de alarma o dudas clínicas, recomiéndale
  que consulte con un profesional sanitario.

Recuerda: las calorías gastadas (Whoop/actividad) son informativas y NO se restan
del objetivo diario; el objetivo ya incluye un factor de actividad."""


GREETING = (
    '¡Hola! Soy tu entrenador. Tengo delante tu comida, tus entrenamientos, tu '
    'peso y tus objetivos, así que pregúntame lo que quieras: cómo llevas la '
    'semana, si vas bien de proteína, qué entrenar mañana o por qué el peso no se '
    'mueve. ¿Por dónde empezamos?'
)


# ─────────────────────────── zona horaria ───────────────────────────

def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def local_today() -> date:
    return datetime.now(_tz()).date()


def _day_window(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, datetime.min.time(), tzinfo=_tz())
    return start, start + timedelta(days=1)


def _range_window(desde: date, hasta: date) -> tuple[datetime, datetime]:
    tz = _tz()
    start = datetime.combine(desde, datetime.min.time(), tzinfo=tz)
    end = datetime.combine(hasta, datetime.min.time(), tzinfo=tz) + timedelta(days=1)
    return start, end


# ─────────────────────────── persistencia ───────────────────────────

def get_or_create() -> CoachConversation:
    conv = CoachConversation.query.first()
    if conv is None:
        conv = CoachConversation(messages=[{'role': 'assistant', 'content': GREETING}])
        db.session.add(conv)
        db.session.commit()
    return conv


def reset(conv: CoachConversation) -> None:
    conv.messages = [{'role': 'assistant', 'content': GREETING}]
    db.session.commit()


# ─────────────────────────── contexto base ───────────────────────────

def _profile_context(profile) -> dict:
    return {
        'objetivo': profile.primary_goal,
        'direccion_objetivo': targets_service.infer_direction(profile),
        'edad': profile.age,
        'sexo': profile.sex,
        'altura_cm': profile.height_cm,
        'peso_kg': profile.weight_kg,
        'dias_entreno_objetivo': profile.training_days_per_week,
        'nivel_actividad': profile.activity_level,
        'deportes': profile.sports or [],
        'condiciones_medicas': profile.conditions or [],
        'lesiones_actuales': profile.injuries_current or [],
        'lesiones_pasadas': profile.injuries_past or [],
        'notas_dieta': profile.diet_notes or [],
        'retos': profile.challenges or [],
        'notas': profile.free_notes,
    }


def _compact_week(metrics: dict, include_days: bool = False) -> dict:
    """Cifras de una semana reducidas a lo esencial para el contexto base."""
    nutrition = metrics.get('nutrition', {})
    activity = metrics.get('activity', {})
    energy = metrics.get('energy', {})
    weight = metrics.get('weight', {})

    resumen = {
        'semana': f"{metrics.get('week_start')} a {metrics.get('week_end')}",
        'nutricion': {
            'dias_registrados': nutrition.get('days_logged', 0),
            'media_kcal': nutrition.get('avg_calories', 0),
            'media_proteina': nutrition.get('avg_proteins', 0),
            'media_carbos': nutrition.get('avg_carbs', 0),
            'media_grasa': nutrition.get('avg_fats', 0),
            'media_fibra': nutrition.get('avg_fiber', 0),
        },
        'actividad': {
            'sesiones': activity.get('sessions', 0),
            'minutos': activity.get('minutes', 0),
            'dias_activo': activity.get('days_active', 0),
            'objetivo_dias': activity.get('training_days_target'),
            'por_familia': [
                {'familia': f.get('label'), 'sesiones': f.get('sessions'),
                 'minutos': f.get('minutes')}
                for f in activity.get('by_family', [])
            ],
        },
        'gasto': {
            'dias_con_dato': energy.get('days_recorded', 0),
            'media_kcal_gastadas': energy.get('avg_burned'),
        },
        'peso': {
            'inicio': weight.get('start'),
            'fin': weight.get('end'),
            'variacion': weight.get('delta'),
        },
    }
    adherence = nutrition.get('adherence')
    if adherence:
        resumen['nutricion']['adherencia'] = {
            'objetivo_kcal': adherence.get('calories_target'),
            'media_vs_objetivo_pct': adherence.get('avg_calories_vs_target_pct'),
            'dias_en_objetivo': adherence.get('days_within_target'),
            'dias_pasado': adherence.get('days_over_target'),
            'dias_con_proteina_ok': adherence.get('days_meeting_protein'),
        }
    if include_days:
        resumen['nutricion']['dias'] = nutrition.get('days', [])
    return resumen


def _composition_of(entry: dict) -> dict | None:
    """Composición corporal (báscula Withings) de una pesada, compacta y solo con
    los valores presentes. None si esa pesada no trae composición (p. ej. manual)."""
    if not entry or not entry.get('has_composition'):
        return None
    campos = {
        'grasa_pct': entry.get('fat_ratio'),
        'musculo_pct': entry.get('muscle_ratio'),
        'hueso_pct': entry.get('bone_ratio'),
        'agua_pct': entry.get('water_ratio'),
        'musculo_kg': entry.get('muscle_mass_kg'),
        'grasa_kg': entry.get('fat_mass_kg'),
    }
    return {k: v for k, v in campos.items() if v is not None}


def _weight_context(profile) -> dict:
    """Estado y evolución del peso + composición corporal, compacto: lo esencial
    y las últimas pesadas (con su composición si la báscula la trajo)."""
    resumen = weight_service.summary(profile)
    entries = resumen.get('entries') or []

    pesadas = []
    for e in entries[-8:]:  # las más recientes, ya en orden cronológico
        fila = {'fecha': e.get('measured_on'), 'kg': e.get('weight_kg')}
        comp = _composition_of(e)
        if comp:
            fila['composicion'] = comp
        pesadas.append(fila)

    return {
        'actual_kg': resumen.get('current'),
        'cambio_ultima_pesada': resumen.get('change_last'),
        'cambio_total': resumen.get('change_total'),
        'dias_desde_ultima': resumen.get('days_since'),
        # Composición de la última pesada, para tenerla a mano.
        'composicion_actual': _composition_of(resumen.get('current_entry') or {}),
        'ultimas_pesadas': pesadas,
    }


def _recent_weeks(today: date) -> list[dict]:
    """Semana en curso (con detalle diario) + las CONTEXT_WEEKS anteriores."""
    salida = []
    for i in range(CONTEXT_WEEKS + 1):
        anchor = today - timedelta(days=7 * i)
        week = weekly_review_service.resolve_week(anchor)
        metrics = weekly_review_service.compute_metrics(week)
        if not metrics.get('has_data') and not week['is_current']:
            continue
        salida.append(_compact_week(metrics, include_days=week['is_current']))
    return salida


def _base_context(profile, targets) -> str:
    today = local_today()
    partes = [
        f'FECHA DE HOY: {today.isoformat()} (semana empieza en lunes).',
        '',
        'PERFIL DEL USUARIO:',
        json.dumps(_profile_context(profile), ensure_ascii=False, indent=2),
        '',
        'OBJETIVOS DIARIOS (calorías y macros que debería cumplir):',
        json.dumps(targets, ensure_ascii=False, indent=2) if targets
        else '(sin objetivos: falta completar el perfil para calcularlos)',
        '',
        'SEGUIMIENTO DE PESO:',
        json.dumps(_weight_context(profile), ensure_ascii=False),
        '',
        'RESUMEN POR SEMANAS (la primera es la semana en curso, con su detalle '
        'diario; el resto son semanas cerradas recientes):',
        json.dumps(_recent_weeks(today), ensure_ascii=False, indent=2),
    ]
    return '\n'.join(partes)


# ─────────────────────────── herramientas ───────────────────────────

def _log_name(log: FoodLog) -> str:
    items = log.items or []
    nombres = [str(i.get('name', '')).strip() for i in items if str(i.get('name', '')).strip()]
    if nombres:
        return ', '.join(nombres)
    if log.description:
        return str(log.description).strip()
    detectados = log.foods_detected or []
    nombres = [str(i.get('name', '')).strip() for i in detectados if str(i.get('name', '')).strip()]
    return ', '.join(nombres) if nombres else 'Comida sin nombre'


def _foods_in(window_start: datetime, window_end: datetime) -> list[dict]:
    logs = (
        FoodLog.query
        .filter(FoodLog.created_at >= window_start, FoodLog.created_at < window_end)
        .order_by(FoodLog.created_at.asc())
        .all()
    )
    tz = _tz()
    salida = []
    for log in logs:
        created = log.created_at
        if created is not None and created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        salida.append({
            'fecha': created.astimezone(tz).date().isoformat() if created else None,
            'hora': created.astimezone(tz).strftime('%H:%M') if created else None,
            'tipo': log.meal_type,
            'nombre': _log_name(log),
            'kcal': round(log.total_calories or 0, 1),
            'proteina': round(log.proteins or 0, 1),
            'carbos': round(log.carbs or 0, 1),
            'grasa': round(log.fats or 0, 1),
            'fibra': round(log.fiber or 0, 1),
            'notas': log.notes or None,
        })
    return salida


def _activities_in(window_start: datetime, window_end: datetime) -> list[dict]:
    sesiones = (
        Activity.query
        .filter(Activity.started_at >= window_start, Activity.started_at < window_end)
        .order_by(Activity.started_at.asc())
        .limit(MAX_ACTIVITIES)
        .all()
    )
    tz = _tz()
    salida = []
    for a in sesiones:
        started = a.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        familia = activity_service.family_of(a.activity_type, a.sport_name)
        etiqueta = next(
            (f['label'] for f in activity_service.FAMILIES if f['key'] == familia), familia
        )
        salida.append({
            'fecha': started.astimezone(tz).date().isoformat() if started else None,
            'hora': started.astimezone(tz).strftime('%H:%M') if started else None,
            'deporte': a.sport_name or etiqueta,
            'familia': etiqueta,
            'duracion_min': a.duration_min,
            'kcal': round(a.calories, 1) if a.calories is not None else None,
            'sensacion_1a5': a.feeling,
            'fuente': a.source,
            'notas': a.notes or None,
            'metricas_whoop': a.metrics or None,
        })
    return salida


def _parse_date(value) -> date:
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        raise AnalysisError(f'Fecha no válida: {value!r}')


def _clamp_range(desde: date, hasta: date) -> tuple[date, date]:
    if hasta < desde:
        desde, hasta = hasta, desde
    if (hasta - desde).days > MAX_RANGE_DAYS:
        desde = hasta - timedelta(days=MAX_RANGE_DAYS)
    return desde, hasta


def _tool_consultar_dia(args: dict) -> dict:
    day = _parse_date(args.get('fecha'))
    start, end = _day_window(day)
    energy = EnergyExpenditure.query.filter_by(measured_on=day).first()
    profile = profile_service.get_or_create()
    targets = targets_service.compute(profile, profile_service.estimate_energy(profile))
    comidas = _foods_in(start, end)
    return {
        'fecha': day.isoformat(),
        'comidas': comidas,
        'totales_comida': {
            'kcal': round(sum(c['kcal'] for c in comidas), 1),
            'proteina': round(sum(c['proteina'] for c in comidas), 1),
            'carbos': round(sum(c['carbos'] for c in comidas), 1),
            'grasa': round(sum(c['grasa'] for c in comidas), 1),
            'fibra': round(sum(c['fibra'] for c in comidas), 1),
        },
        'actividades': _activities_in(start, end),
        'gasto_energetico_kcal': round(energy.calories, 1) if energy else None,
        'objetivos_dia': targets,
    }


def _tool_consultar_nutricion(args: dict) -> dict:
    desde, hasta = _clamp_range(_parse_date(args.get('desde')), _parse_date(args.get('hasta')))
    start, end = _range_window(desde, hasta)
    dias = weekly_review_service._nutrition_days(start, end)
    logged = [d for d in dias if d['meals'] > 0]
    n = len(logged)
    medias = {}
    if n:
        for k in ('calories', 'proteins', 'carbs', 'fats', 'fiber'):
            medias[k] = round(sum(d[k] for d in logged) / n, 1)
    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'dias_registrados': n,
        'medias_diarias': medias,
        'dias': dias,
    }


def _tool_consultar_actividades(args: dict) -> dict:
    desde, hasta = _clamp_range(_parse_date(args.get('desde')), _parse_date(args.get('hasta')))
    start, end = _range_window(desde, hasta)
    actividades = _activities_in(start, end)
    return {
        'desde': desde.isoformat(),
        'hasta': hasta.isoformat(),
        'total_sesiones': len(actividades),
        'minutos_totales': sum(a['duracion_min'] or 0 for a in actividades),
        'actividades': actividades,
    }


_TOOL_HANDLERS = {
    'consultar_dia': _tool_consultar_dia,
    'consultar_nutricion': _tool_consultar_nutricion,
    'consultar_actividades': _tool_consultar_actividades,
}


def _run_tool(name: str, tool_input) -> dict:
    handler = _TOOL_HANDLERS.get(name)
    if handler is None:
        return {'error': f'Herramienta desconocida: {name}'}
    args = tool_input if isinstance(tool_input, dict) else {}
    try:
        return handler(args)
    except AnalysisError as exc:
        return {'error': str(exc)}
    except Exception:  # noqa: BLE001 - el error va al modelo, no rompe el chat
        current_app.logger.exception('Fallo ejecutando la herramienta %s', name)
        return {'error': 'No se pudo consultar ese dato.'}


# ─────────────────────────── chat (bucle del agente) ───────────────────────────

def _text_of(response) -> str:
    return ''.join(b.text for b in response.content if b.type == 'text').strip()


def _api_key() -> str:
    key = current_app.config.get('ANTHROPIC_API_KEY', '') or ''
    if not key or key.startswith('sk-ant-api03-REEMPLAZA'):
        raise AnalysisError('API key de Anthropic no configurada.')
    return key


def chat(conv: CoachConversation, message: str) -> dict:
    """Un turno de charla con el entrenador. Resuelve las herramientas que pida y
    devuelve la respuesta final en texto."""
    client = anthropic.Anthropic(api_key=_api_key())
    model = current_app.config['ANTHROPIC_MODEL']

    profile = profile_service.get_or_create()
    targets = targets_service.compute(profile, profile_service.estimate_energy(profile))
    system = SYSTEM + '\n\n' + _base_context(profile, targets)

    visible = list(conv.messages or [])
    visible.append({'role': 'user', 'content': message})
    recent = visible[-HISTORY_TURNS:]

    api_messages = [{'role': m['role'], 'content': m['content']} for m in recent]

    reply = ''
    for _ in range(MAX_TOOL_ITERATIONS):
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system,
            tools=coach_tool.TOOLS,
            messages=api_messages,
        )

        if response.stop_reason == 'refusal':
            raise AnalysisError('El modelo rechazó responder a este mensaje.')

        if response.stop_reason == 'tool_use':
            tool_results = []
            for block in response.content:
                if block.type == 'tool_use':
                    result = _run_tool(block.name, block.input)
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps(result, ensure_ascii=False),
                    })
            api_messages.append({'role': 'assistant', 'content': response.content})
            api_messages.append({'role': 'user', 'content': tool_results})
            continue

        reply = _text_of(response)
        break

    # Si se agotaron las vueltas sin respuesta final, una última sin herramientas.
    if not reply:
        response = client.messages.create(
            model=model,
            max_tokens=1500,
            system=system,
            messages=api_messages,
        )
        reply = _text_of(response)

    if not reply:
        raise AnalysisError('El modelo no devolvió respuesta.')

    visible.append({'role': 'assistant', 'content': reply})
    conv.messages = visible[-80:]
    db.session.commit()
    return {'reply': reply}
