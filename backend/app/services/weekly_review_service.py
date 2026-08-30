"""Resumen semanal de nutrición y actividad (lunes→domingo).

Genera, guarda y consulta un resumen por semana. La generación es perezosa: la
primera vez que se consulta una semana ya cerrada (estamos en una semana
posterior) se calculan sus cifras, se pide al LLM que las redacte y se guarda la
fila. Regenerar recalcula y corrige la misma fila.

El reparto de responsabilidades es deliberado:
- **Las cifras se calculan aquí, en SQL/Python** (medias, adherencia a objetivos,
  sesiones por familia, peso, gasto). Se congelan en `metrics` para que la
  comparativa de la semana siguiente sea exacta sin recalcular.
- **El LLM solo redacta** sobre esas cifras (lo bueno, a mejorar, comparativa,
  recomendaciones). Nunca inventa números: recibe los de esta semana y los de la
  anterior y los interpreta a la luz del perfil y los objetivos.

La semana empieza en lunes y se calcula en `APP_TIMEZONE`, igual que el resto de
agregados de la app (`(created_at AT TIME ZONE :tz)::date`).
"""

import json
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import anthropic
from flask import current_app
from sqlalchemy import text

from .. import db
from ..models.activity import Activity
from ..models.energy_expenditure import EnergyExpenditure
from ..models.weekly_review import WeeklyReview
from ..models.weight_entry import WeightEntry
from . import (activity_service, body_service, profile_service, targets_service,
               weekly_review_tool)
from .claude_service import AnalysisError

# Umbral de adherencia: se considera "en objetivo" un día cuyas calorías quedan
# a menos de un 10% del objetivo. Un margen más estrecho penalizaría el ruido
# normal de estimar porciones a ojo.
ADHERENCE_TOLERANCE = 0.10
PROTEIN_HIT_SHARE = 0.90  # cumplir proteína = llegar al 90% del objetivo


SYSTEM = """Eres el entrenador y nutricionista de esta persona y le escribes su
resumen de la semana. Hablas en español, de tú, cercano y directo, sin
tecnicismos innecesarios ni paja.

Reglas:
- Usa SOLO las cifras que te doy. No inventes números ni completes lo que falte.
- Cada elogio o crítica va anclado a una cifra concreta (kcal, gramos de
  proteína, sesiones, minutos, peso, composición corporal, medidas de cinta).
- Si hay datos de composición corporal (grasa, músculo, hueso, agua de la
  báscula, en `weight.composition`), di explícitamente si hay AVANCE o retroceso
  respecto al inicio de la semana o a la semana anterior, anclado a los
  porcentajes/kg (p. ej. músculo, grasa). Es clave para el objetivo de
  recomposición. Si no hay datos de composición esta semana, no lo menciones.
- Si hay medidas corporales de cinta (`body`: cintura, abdomen, pectoral,
  bíceps), comenta el progreso: cita el valor actual y el cambio respecto a la
  toma anterior (p. ej. cintura −1 cm). Son periódicas, no semanales, así que no
  pasa nada si no hubo toma esta semana. Si no hay medidas, no lo menciones.
- Ten en cuenta el objetivo declarado (perder grasa, mantener, ganar, recomp) y
  las lesiones o condiciones médicas: no recomiendes nada que las ignore.
- Sé honesto pero motivador: si la semana fue floja, dilo, pero con una salida.
- Para la comparativa, valora el conjunto (nutrición Y actividad), no un único
  número. Si no hay datos de la semana anterior, la tendencia es "sin_datos".
"""


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _tz_name() -> str:
    return current_app.config['APP_TIMEZONE']


def local_today() -> date:
    return datetime.now(_tz()).date()


# ─────────────────────────── resolución de la semana ───────────────────────────

def resolve_week(anchor: date) -> dict:
    """Semana lunes→domingo que contiene `anchor`, con su estado temporal."""
    monday = anchor - timedelta(days=anchor.weekday())  # weekday(): lunes = 0
    sunday = monday + timedelta(days=6)
    iso_year, iso_week, _ = monday.isocalendar()
    today = local_today()

    return {
        'iso_year': iso_year,
        'iso_week': iso_week,
        'week_start': monday,
        'week_end': sunday,
        # En curso: hoy cae dentro de la semana.
        'is_current': monday <= today <= sunday,
        # Cerrada: ya estamos en una semana posterior. Solo entonces se genera y
        # se guarda de forma automática (perezosa).
        'is_closed': today > sunday,
        # Se puede (re)generar bajo petición desde su domingo (día en que se
        # cierra la semana); nunca entre semana ni en una semana futura.
        'can_generate': today >= sunday,
    }


def _window(week: dict) -> tuple[datetime, datetime]:
    """Ventana [inicio, fin) de la semana en la zona del usuario, con offset."""
    tz = _tz()
    start = datetime.combine(week['week_start'], datetime.min.time(), tzinfo=tz)
    return start, start + timedelta(days=7)


# ─────────────────────────── cálculo de cifras ───────────────────────────

def _nutrition_days(window_start: datetime, window_end: datetime) -> list[dict]:
    """Totales por día natural de la semana. Solo los días con comidas."""
    rows = db.session.execute(
        text("""
            SELECT (created_at AT TIME ZONE :tz)::date AS day,
                   COUNT(*)                         AS meals,
                   COALESCE(SUM(total_calories), 0) AS calories,
                   COALESCE(SUM(proteins), 0)       AS proteins,
                   COALESCE(SUM(carbs), 0)          AS carbs,
                   COALESCE(SUM(fats), 0)           AS fats,
                   COALESCE(SUM(fiber), 0)          AS fiber,
                   COALESCE(SUM(saturated_fat), 0)  AS saturated_fat,
                   COALESCE(SUM(salt), 0)           AS salt
            FROM food_logs
            WHERE created_at >= :start AND created_at < :end
            GROUP BY 1
            ORDER BY 1
        """),
        {'tz': _tz_name(), 'start': window_start, 'end': window_end},
    ).mappings().all()

    return [
        {
            'date': row['day'].isoformat(),
            'meals': int(row['meals']),
            'calories': round(float(row['calories']), 1),
            'proteins': round(float(row['proteins']), 1),
            'carbs': round(float(row['carbs']), 1),
            'fats': round(float(row['fats']), 1),
            'fiber': round(float(row['fiber']), 1),
            'saturated_fat': round(float(row['saturated_fat']), 1),
            'salt': round(float(row['salt']), 1),
        }
        for row in rows
    ]


_MACROS = ('calories', 'proteins', 'carbs', 'fats', 'fiber', 'saturated_fat', 'salt')


def _nutrition_metrics(days: list[dict], targets: dict | None) -> dict:
    """Medias diarias y adherencia a los objetivos, sobre los días registrados.

    Las medias se calculan solo sobre días con registros: incluir los días
    vacíos como 0 kcal daría una media engañosa (igual criterio que /summary).
    """
    logged = [d for d in days if d['meals'] > 0]
    n = len(logged)

    averages = {
        f'avg_{k}': round(sum(d[k] for d in logged) / n, 1) if n else 0.0
        for k in _MACROS
    }

    metrics = {
        'days_logged': n,
        'total_calories': round(sum(d['calories'] for d in logged), 1),
        **averages,
        'days': logged,
    }

    if targets and n:
        cal_target = targets.get('calories') or 0
        prot_target = targets.get('proteins') or 0
        within = sum(
            1 for d in logged
            if cal_target and abs(d['calories'] - cal_target) <= cal_target * ADHERENCE_TOLERANCE
        )
        over = sum(
            1 for d in logged
            if cal_target and d['calories'] > cal_target * (1 + ADHERENCE_TOLERANCE)
        )
        protein_hit = sum(
            1 for d in logged
            if prot_target and d['proteins'] >= prot_target * PROTEIN_HIT_SHARE
        )
        metrics['adherence'] = {
            'calories_target': cal_target,
            'protein_target': prot_target,
            'avg_calories_vs_target_pct': (
                round(averages['avg_calories'] / cal_target * 100) if cal_target else None
            ),
            'days_within_target': within,
            'days_over_target': over,
            'days_meeting_protein': protein_hit,
        }

    return metrics


def _activity_metrics(window_start: datetime, window_end: datetime,
                      training_days_target) -> dict:
    """Sesiones, minutos y desglose por familia de la semana."""
    sesiones = (
        Activity.query
        .filter(Activity.started_at >= window_start, Activity.started_at < window_end)
        .all()
    )

    tz = _tz()
    dias_activos = set()
    por_familia: dict[str, dict] = {}
    minutos_total = 0
    calorias_total = 0.0

    for a in sesiones:
        familia = activity_service.family_of(a.activity_type, a.sport_name)
        started = a.started_at
        if started is not None and started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started is not None:
            dias_activos.add(started.astimezone(tz).date())

        minutos = a.duration_min or 0
        minutos_total += minutos
        calorias_total += a.calories or 0

        acc = por_familia.setdefault(familia, {'sessions': 0, 'minutes': 0})
        acc['sessions'] += 1
        acc['minutes'] += minutos

    # En el orden fijo de familias, solo las que tienen actividad.
    by_family = [
        {
            'family': fam['key'],
            'label': fam['label'],
            'color': fam['color'],
            'sessions': por_familia[fam['key']]['sessions'],
            'minutes': por_familia[fam['key']]['minutes'],
        }
        for fam in activity_service.FAMILIES
        if fam['key'] in por_familia
    ]

    return {
        'sessions': len(sesiones),
        'minutes': minutos_total,
        'days_active': len(dias_activos),
        'training_days_target': training_days_target,
        'calories': round(calorias_total, 1),
        'by_family': by_family,
    }


def _energy_metrics(week: dict) -> dict:
    """Gasto energético del día (informativo): días registrados y media."""
    filas = (
        EnergyExpenditure.query
        .filter(EnergyExpenditure.measured_on >= week['week_start'],
                EnergyExpenditure.measured_on <= week['week_end'])
        .all()
    )
    if not filas:
        return {'days_recorded': 0, 'avg_burned': None}
    return {
        'days_recorded': len(filas),
        'avg_burned': round(sum(e.calories for e in filas) / len(filas), 1),
    }


# Métricas de composición corporal (báscula Withings) y su etiqueta para el LLM.
_COMPOSITION_METRICS = (
    ('fat_ratio', 'grasa_pct'),
    ('muscle_ratio', 'musculo_pct'),
    ('bone_ratio', 'hueso_pct'),
    ('water_ratio', 'agua_pct'),
    ('muscle_mass_kg', 'musculo_kg'),
    ('fat_mass_kg', 'grasa_kg'),
)


def _composition_metrics(filas: list) -> dict:
    """Inicio, fin y variación de cada métrica de composición dentro de la semana.

    Solo cuentan las pesadas de báscula que traen cada dato (una pesada manual no
    lleva composición); una métrica sin datos en la semana se omite.
    """
    dicts = [f.to_dict() for f in filas]  # ya en orden ascendente por fecha
    out: dict = {}
    for key, label in _COMPOSITION_METRICS:
        serie = [d[key] for d in dicts if d.get(key) is not None]
        if not serie:
            continue
        out[label] = {
            'inicio': serie[0],
            'fin': serie[-1],
            'variacion': round(serie[-1] - serie[0], 1) if len(serie) > 1 else None,
        }
    return out


def _weight_metrics(week: dict) -> dict:
    """Peso y composición corporal al principio y al final de la semana, y su
    variación."""
    filas = (
        WeightEntry.query
        .filter(WeightEntry.measured_on >= week['week_start'],
                WeightEntry.measured_on <= week['week_end'])
        .order_by(WeightEntry.measured_on.asc())
        .all()
    )
    if not filas:
        return {'entries': 0, 'start': None, 'end': None, 'delta': None, 'composition': {}}

    start_kg = filas[0].weight_kg
    end_kg = filas[-1].weight_kg
    return {
        'entries': len(filas),
        'start': round(start_kg, 1),
        'end': round(end_kg, 1),
        'delta': round(end_kg - start_kg, 1) if len(filas) > 1 else None,
        # Composición corporal de la báscula (grasa, músculo, hueso, agua).
        'composition': _composition_metrics(filas),
    }


def _body_metrics() -> dict:
    """Medidas corporales de cinta (cintura, abdomen, pectoral, bíceps) con su
    último valor y variación. Son periódicas (p. ej. mensuales), así que no se
    limitan a la semana: se da la última toma y el cambio respecto a la anterior,
    para poder comentar el progreso aunque no haya toma esta misma semana."""
    resumen = body_service.measurement_summary()
    if not resumen['entries']:
        return {'entries': 0}
    return {
        'entries': len(resumen['entries']),
        'ultima_toma': (resumen['latest'] or {}).get('measured_on'),
        'medidas': {
            info['label']: {
                'cm': info['current'],
                'cambio_desde_anterior': info['change_last'],
                'cambio_total': info['change_total'],
            }
            for info in resumen['changes'].values()
        },
    }


def _daily_targets() -> dict | None:
    profile = profile_service.get_or_create()
    return targets_service.compute(profile, profile_service.estimate_energy(profile))


def compute_metrics(week: dict) -> dict:
    """Todas las cifras de la semana, listas para congelar y para el LLM."""
    window_start, window_end = _window(week)
    profile = profile_service.get_or_create()
    targets = _daily_targets()

    days = _nutrition_days(window_start, window_end)
    nutrition = _nutrition_metrics(days, targets)
    activity = _activity_metrics(window_start, window_end, profile.training_days_per_week)

    return {
        'week_start': week['week_start'].isoformat(),
        'week_end': week['week_end'].isoformat(),
        'nutrition': nutrition,
        'activity': activity,
        'energy': _energy_metrics(week),
        'weight': _weight_metrics(week),
        'body': _body_metrics(),
        'targets': targets,
        'has_data': nutrition['days_logged'] > 0 or activity['sessions'] > 0,
    }


# ─────────────────────────── narrativa (LLM) ───────────────────────────

def _profile_context(profile) -> dict:
    """Lo del perfil que el LLM necesita para interpretar y recomendar."""
    return {
        'objetivo': profile.primary_goal,
        'direccion_objetivo': targets_service.infer_direction(profile),
        'edad': profile.age,
        'sexo': profile.sex,
        'peso_kg': profile.weight_kg,
        'dias_entreno_objetivo': profile.training_days_per_week,
        'deportes': profile.sports or [],
        'condiciones_medicas': profile.conditions or [],
        'lesiones_actuales': profile.injuries_current or [],
        'notas': profile.free_notes,
    }


def _user_content(metrics: dict, previous: dict | None, profile) -> str:
    partes = [
        'Redacta el resumen de esta semana para el usuario.',
        '',
        'PERFIL Y OBJETIVO:',
        json.dumps(_profile_context(profile), ensure_ascii=False, indent=2),
        '',
        'CIFRAS DE ESTA SEMANA:',
        json.dumps(metrics, ensure_ascii=False, indent=2),
        '',
    ]
    if previous:
        partes += [
            'CIFRAS DE LA SEMANA ANTERIOR (para la comparativa):',
            json.dumps(previous, ensure_ascii=False, indent=2),
        ]
    else:
        partes.append('No hay datos de la semana anterior: tendencia = "sin_datos".')
    return '\n'.join(partes)


def _clean_list(value, limit: int = 4) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def _normalize_narrative(data) -> dict:
    if not isinstance(data, dict):
        data = {}
    comp = data.get('comparativa') if isinstance(data.get('comparativa'), dict) else {}
    tendencia = str(comp.get('tendencia', 'sin_datos')).strip().lower()
    if tendencia not in {'mejor', 'igual', 'peor', 'sin_datos'}:
        tendencia = 'sin_datos'
    return {
        'resumen': str(data.get('resumen', '')).strip()[:800],
        'lo_bueno': _clean_list(data.get('lo_bueno')),
        'a_mejorar': _clean_list(data.get('a_mejorar')),
        'comparativa': {
            'tendencia': tendencia,
            'detalle': str(comp.get('detalle', '')).strip()[:800],
            'factores': _clean_list(comp.get('factores'), 3),
        },
        'recomendaciones': _clean_list(data.get('recomendaciones'), 3),
    }


def _empty_narrative() -> dict:
    """Semana sin datos: no se llama al LLM, se guarda un texto fijo."""
    return {
        'resumen': 'No hay datos suficientes esta semana: no se registraron '
                   'comidas ni actividad, así que no hay nada que analizar.',
        'lo_bueno': [],
        'a_mejorar': ['Registrar al menos las comidas principales para poder '
                      'analizar la semana.'],
        'comparativa': {'tendencia': 'sin_datos', 'detalle': 'Sin registros que comparar.',
                        'factores': []},
        'recomendaciones': ['Apunta la comida en cuanto la tengas delante; con una '
                            'foto es cuestión de segundos.'],
    }


def _api_key() -> str:
    key = current_app.config.get('ANTHROPIC_API_KEY', '') or ''
    if not key or key.startswith('sk-ant-api03-REEMPLAZA'):
        raise AnalysisError('API key de Anthropic no configurada.')
    return key


def _call_llm(metrics: dict, previous: dict | None) -> tuple[dict, str]:
    """Pide al LLM que redacte el resumen. Devuelve (narrativa, modelo)."""
    profile = profile_service.get_or_create()
    client = anthropic.Anthropic(api_key=_api_key())
    model = current_app.config['ANTHROPIC_COACH_MODEL']

    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system=SYSTEM,
        tools=[weekly_review_tool.TOOL],
        tool_choice={'type': 'tool', 'name': weekly_review_tool.TOOL_NAME},
        messages=[{'role': 'user', 'content': _user_content(metrics, previous, profile)}],
    )

    if response.stop_reason == 'refusal':
        raise AnalysisError('El modelo rechazó redactar el resumen.')

    block = next(
        (b for b in response.content
         if b.type == 'tool_use' and b.name == weekly_review_tool.TOOL_NAME),
        None,
    )
    if block is None:
        raise AnalysisError('El modelo no usó la herramienta de resumen.')

    data = block.input if isinstance(block.input, dict) else {}
    return _normalize_narrative(data), model


# ─────────────────────────── persistencia / orquestación ───────────────────────────

def get_stored(iso_year: int, iso_week: int) -> WeeklyReview | None:
    return WeeklyReview.query.filter_by(iso_year=iso_year, iso_week=iso_week).first()


def _previous_metrics(week: dict) -> dict | None:
    """Cifras de la semana anterior, para la comparativa. None si no hubo datos."""
    prev_anchor = week['week_start'] - timedelta(days=7)
    prev_week = resolve_week(prev_anchor)
    metrics = compute_metrics(prev_week)
    return metrics if metrics['has_data'] else None


def generate(week: dict) -> WeeklyReview:
    """Calcula, redacta (o texto fijo si no hay datos) y guarda la semana."""
    metrics = compute_metrics(week)
    previous = _previous_metrics(week)

    if not metrics['has_data']:
        narrative, model = _empty_narrative(), None
    else:
        narrative, model = _call_llm(metrics, previous)

    review = get_stored(week['iso_year'], week['iso_week'])
    if review is None:
        review = WeeklyReview(iso_year=week['iso_year'], iso_week=week['iso_week'])
        db.session.add(review)

    review.week_start = week['week_start']
    review.week_end = week['week_end']
    review.metrics = metrics
    review.narrative = narrative
    review.model = model
    review.generated_at = datetime.now(timezone.utc)

    db.session.commit()
    return review


def _payload(week: dict, review: WeeklyReview | None,
             metrics: dict, previous: dict | None) -> dict:
    """Respuesta de una semana: cifras + narrativa (si la hay) + estado."""
    return {
        'week': {
            'iso_year': week['iso_year'],
            'iso_week': week['iso_week'],
            'week_start': week['week_start'].isoformat(),
            'week_end': week['week_end'].isoformat(),
        },
        'is_current': week['is_current'],
        'is_closed': week['is_closed'],
        'can_generate': week['can_generate'],
        'generated': review is not None,
        'metrics': metrics,
        'previous': previous,
        'narrative': review.narrative if review else None,
        'model': review.model if review else None,
        'generated_at': review.to_dict()['generated_at'] if review else None,
    }


def weekly_payload(anchor: date) -> dict:
    """Semana que contiene `anchor`. Genera de forma perezosa si ya está cerrada.

    - Si ya está guardada: se sirve tal cual (cifras congeladas + narrativa).
    - Si está cerrada y aún no existe: se genera, se guarda y se devuelve.
    - Si está en curso (o no se puede generar): se devuelve una vista previa con
      las cifras vivas y sin narrativa.
    """
    week = resolve_week(anchor)
    stored = get_stored(week['iso_year'], week['iso_week'])

    if stored is not None:
        previous = _previous_metrics(week)
        return _payload(week, stored, stored.metrics or {}, previous)

    if week['is_closed']:
        try:
            review = generate(week)
            previous = _previous_metrics(week)
            return _payload(week, review, review.metrics or {}, previous)
        except AnalysisError as exc:
            db.session.rollback()
            current_app.logger.warning('No se pudo generar el resumen semanal: %s', exc)

    # Semana en curso, o generación no disponible: vista previa en vivo.
    metrics = compute_metrics(week)
    previous = _previous_metrics(week)
    return _payload(week, None, metrics, previous)


def regenerate(anchor: date) -> dict:
    """Fuerza el recálculo y la reescritura de la semana. Requiere que se pueda
    generar (su domingo ha llegado) y propaga AnalysisError si el LLM falla."""
    week = resolve_week(anchor)
    if not week['can_generate']:
        raise ValueError('El resumen de una semana solo se puede generar a partir '
                         'de su domingo.')
    review = generate(week)
    previous = _previous_metrics(week)
    return _payload(week, review, review.metrics or {}, previous)


def list_reviews(limit: int = 26) -> list[dict]:
    """Resúmenes guardados, de la semana más reciente a la más antigua."""
    filas = (
        WeeklyReview.query
        .order_by(WeeklyReview.week_start.desc())
        .limit(limit)
        .all()
    )

    salida = []
    for r in filas:
        metrics = r.metrics or {}
        narrative = r.narrative or {}
        nutrition = metrics.get('nutrition', {})
        activity = metrics.get('activity', {})
        salida.append({
            'week_start': r.week_start.isoformat() if r.week_start else None,
            'week_end': r.week_end.isoformat() if r.week_end else None,
            'iso_year': r.iso_year,
            'iso_week': r.iso_week,
            # Lo justo para la tarjeta de la lista, sin volcar todo el resumen.
            'resumen': narrative.get('resumen', ''),
            'tendencia': (narrative.get('comparativa') or {}).get('tendencia', 'sin_datos'),
            'avg_calories': nutrition.get('avg_calories', 0),
            'days_logged': nutrition.get('days_logged', 0),
            'sessions': activity.get('sessions', 0),
        })
    return salida
