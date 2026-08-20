"""Biblioteca de platos y alimentos reutilizables.

La biblioteca se llena sola: cada comida registrada crea (o reutiliza) una
plantilla. Lo que se come a menudo sube en el ranking y el resto se hunde, sin
pedirle al usuario que decida al guardar si repetirá algo.
"""

import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy.orm.attributes import flag_modified

from .. import db
from ..models.food_template import FoodTemplate

MACRO_KEYS = ('calories', 'proteins', 'carbs', 'fats', 'fiber', 'saturated_fat', 'salt')

# Peso extra por comer algo en la misma franja del día (desayuno, comida...).
SLOT_WEIGHT = 2
# A los RECENCY_HALFLIFE_DAYS días sin usarse, la puntuación cae a la mitad.
RECENCY_HALFLIFE_DAYS = 14


def normalize_name(name: str) -> str:
    """Clave de identidad: minúsculas, sin acentos ni puntuación ni dobles espacios."""
    text = unicodedata.normalize('NFKD', (name or '').strip().lower())
    text = ''.join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def score_template(template: FoodTemplate, meal_type: str | None, now: datetime) -> float:
    """Frecuencia ponderada por franja horaria y decaída por antigüedad."""
    counts = template.meal_type_counts or {}
    slot_count = counts.get(meal_type, 0) if meal_type else 0
    base = template.times_used + SLOT_WEIGHT * slot_count

    last_used = _aware(template.last_used_at)
    if last_used is None:
        return base * 0.1

    days = max((now - last_used).total_seconds() / 86400, 0)
    return base / (1 + days / RECENCY_HALFLIFE_DAYS)


def find_by_name(name: str) -> FoodTemplate | None:
    key = normalize_name(name)
    if not key:
        return None
    return FoodTemplate.query.filter_by(normalized_name=key).first()


def upsert_template(
    *,
    name: str,
    macros: dict,
    kind: str = 'dish',
    quantity_label: str = '',
    components: list | None = None,
    photo_path: str | None = None,
    source: str = 'ai',
    analysis: dict | None = None,
) -> FoodTemplate | None:
    """Devuelve la plantilla con ese nombre, creándola si no existía.

    No pisa los macros de una plantilla existente: si el usuario los corrigió
    desde la biblioteca, una comida nueva no debe revertir esa corrección.
    """
    key = normalize_name(name)
    if not key:
        return None

    template = FoodTemplate.query.filter_by(normalized_name=key).first()
    if template:
        # Solo rellenamos huecos (p. ej. la primera foto del plato).
        if photo_path and not template.photo_path:
            template.photo_path = photo_path
        if components and not template.components:
            template.components = components
        if analysis and not template.analysis:
            template.analysis = analysis
        if template.archived:
            template.archived = False
        return template

    template = FoodTemplate(
        kind=kind,
        name=name.strip()[:200],
        normalized_name=key[:200],
        quantity_label=(quantity_label or '')[:80],
        components=components or [],
        analysis=analysis or {},
        photo_path=photo_path,
        source=source,
        times_used=0,
        meal_type_counts={},
        **{k: float(macros.get(k, 0) or 0) for k in MACRO_KEYS},
    )
    db.session.add(template)
    db.session.flush()  # necesitamos el id antes del commit
    return template


def record_usage(template: FoodTemplate, meal_type: str, when: datetime) -> None:
    counts = dict(template.meal_type_counts or {})
    counts[meal_type] = counts.get(meal_type, 0) + 1

    template.meal_type_counts = counts
    template.times_used = (template.times_used or 0) + 1
    template.last_used_at = when


def suggest(meal_type: str | None, limit: int = 8) -> dict:
    """Sugerencias para la pantalla de añadir: frecuentes en esta franja + recientes."""
    now = datetime.now(timezone.utc)
    candidates = FoodTemplate.query.filter_by(archived=False).all()

    ranked = sorted(candidates, key=lambda t: score_template(t, meal_type, now), reverse=True)
    suggested = [t for t in ranked if t.times_used > 0][:limit]

    suggested_ids = {t.id for t in suggested}
    recent = sorted(
        (t for t in candidates if t.last_used_at and t.id not in suggested_ids),
        key=lambda t: _aware(t.last_used_at),
        reverse=True,
    )[:limit]

    return {
        'suggested': [t.to_dict() for t in suggested],
        'recent': [t.to_dict() for t in recent],
        'total': len(candidates),
    }


def search(query: str, limit: int = 30) -> list[FoodTemplate]:
    """Búsqueda por subcadena sobre el nombre normalizado (tolera acentos)."""
    key = normalize_name(query)
    q = FoodTemplate.query.filter_by(archived=False)
    if key:
        q = q.filter(FoodTemplate.normalized_name.contains(key))

    now = datetime.now(timezone.utc)
    results = q.limit(200).all()
    results.sort(key=lambda t: score_template(t, None, now), reverse=True)
    return results[:limit]


def merge(source_id: int, target_id: int) -> FoodTemplate | None:
    """Funde una plantilla duplicada en otra, sumando su uso."""
    if source_id == target_id:
        return None

    source = db.session.get(FoodTemplate, source_id)
    target = db.session.get(FoodTemplate, target_id)
    if not source or not target:
        return None

    counts = dict(target.meal_type_counts or {})
    for slot, n in (source.meal_type_counts or {}).items():
        counts[slot] = counts.get(slot, 0) + n

    target.meal_type_counts = counts
    target.times_used = (target.times_used or 0) + (source.times_used or 0)

    source_last = _aware(source.last_used_at)
    target_last = _aware(target.last_used_at)
    if source_last and (not target_last or source_last > target_last):
        target.last_used_at = source_last
    if source.photo_path and not target.photo_path:
        target.photo_path = source.photo_path

    db.session.delete(source)
    return target


# ─────────────────── propagación a los registros ───────────────────
#
# Decisión del usuario (2026-08-17): editar un plato de la biblioteca SÍ debe
# corregir los días en los que aparece. Antes se guardaba una copia inmutable;
# ahora se prefiere que el historial refleje siempre los datos corregidos.

def describe_items(items: list[dict]) -> str:
    names = [i.get('name', '') for i in items]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ' + '.join(names)
    return f"{' + '.join(names[:2])} +{len(names) - 2} más"


def logs_using(template_id: int) -> list:
    """Registros que contienen un elemento de esta plantilla."""
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB

    from ..models.food_log import FoodLog

    return (
        FoodLog.query
        .filter(cast(FoodLog.items, JSONB).contains([{'template_id': template_id}]))
        .all()
    )


def propagate_to_logs(template: FoodTemplate) -> int:
    """Reescribe nombre, macros y foto en los registros que usan la plantilla.

    Devuelve cuántos registros se han actualizado.
    """
    logs = logs_using(template.id)
    updated = 0

    for log in logs:
        # Copias, no los dicts cargados: si se mutan in situ, SQLAlchemy compara
        # el valor nuevo con el cargado (que ya viene mutado), no ve diferencia
        # y nunca emite el UPDATE de la columna JSON.
        items = [dict(i) for i in (log.items or [])]
        touched = False

        for item in items:
            if item.get('template_id') != template.id:
                continue
            portion = float(item.get('portion', 1) or 1)
            item['name'] = template.name
            item['quantity'] = template.quantity_label or ''
            # El desglose por porciones también viaja al registro: si corriges
            # los gramos de un ingrediente, el día debe reflejarlo.
            item['components'] = template.components or []
            if template.analysis:
                item['analysis'] = template.analysis
            for key in MACRO_KEYS:
                item[key] = round(getattr(template, key) * portion, 1)
            touched = True

        if not touched:
            continue

        log.items = items
        flag_modified(log, 'items')
        log.description = describe_items(items)[:1000]
        log.foods_detected = [
            {'name': i.get('name', ''), 'quantity': i.get('quantity', ''),
             'calories': round(float(i.get('calories', 0) or 0))}
            for i in items
        ]
        for key in MACRO_KEYS:
            total = round(sum(float(i.get(key, 0) or 0) for i in items), 1)
            setattr(log, 'total_calories' if key == 'calories' else key, total)

        # La foto propia de una comida es el registro de lo que se comió ese
        # día: solo se rellena si no tenía ninguna.
        if template.photo_path and not log.photo_path:
            log.photo_path = template.photo_path

        updated += 1

    return updated


def unlink_from_logs(template_id: int) -> int:
    """Al borrar una plantilla, el historial se conserva pero deja de apuntarla."""
    logs = logs_using(template_id)
    for log in logs:
        items = [dict(i) for i in (log.items or [])]
        for item in items:
            if item.get('template_id') == template_id:
                item['template_id'] = None
        log.items = items
        flag_modified(log, 'items')
    return len(logs)
