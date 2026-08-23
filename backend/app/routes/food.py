import os
import time
import uuid
# OJO: no importar `time` desde datetime aquí; taparía el módulo `time`
# que usa _cleanup_orphan_photos().
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, request, jsonify, send_from_directory, current_app
from sqlalchemy import text
from werkzeug.utils import secure_filename

from .. import db
from ..models.food_log import FoodLog
from ..models.food_template import FoodTemplate
from ..services import (
    activity_service, energy_service, library_service, profile_service, targets_service,
)
from ..services.claude_service import AnalysisError, analyze_food_images, analyze_food_text
from ..services.image_service import UnsupportedImageError, normalize_image
from ..services.library_service import MACRO_KEYS

food_bp = Blueprint('food', __name__)

VALID_MEAL_TYPES = {'breakfast', 'lunch', 'snack', 'dinner'}
VALID_CONFIDENCE = {'high', 'medium', 'low'}
MAX_ITEMS = 30
# Cada imagen cuesta tokens de visión; más de 4 vistas del mismo plato no
# mejora la estimación lo bastante para justificarlo.
MAX_PHOTOS = 4
MIN_PORTION = 0.05
MAX_PORTION = 20


# ─────────────────────────── utilidades ───────────────────────────

def _user_timezone() -> ZoneInfo:
    name = current_app.config['APP_TIMEZONE']
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        current_app.logger.warning('APP_TIMEZONE invalida (%s), usando UTC', name)
        return ZoneInfo('UTC')


def _day_bounds(day: date, days: int = 1) -> tuple[datetime, datetime]:
    """Ventana [inicio, fin) de N días naturales del usuario, con offset.

    Calcularlo en UTC hace que las comidas de madrugada caigan en el día
    anterior (o desaparezcan) para cualquier zona que no sea UTC.
    """
    tz = _user_timezone()
    start_local = datetime.combine(day, datetime.min.time(), tzinfo=tz)
    return start_local, start_local + timedelta(days=days)


def _local_today() -> date:
    return datetime.now(_user_timezone()).date()


def _local_day_bounds() -> tuple[datetime, datetime]:
    return _day_bounds(_local_today())


def _parse_date(value: str | None, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError('Formato de fecha inválido, se espera YYYY-MM-DD.')


def _allowed_file(filename: str) -> bool:
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def _save_normalized_image(image_bytes: bytes) -> str:
    filename = f'{uuid.uuid4().hex}.jpg'
    dest = os.path.join(current_app.config['UPLOAD_FOLDER_ABS'], filename)
    with open(dest, 'wb') as handle:
        handle.write(image_bytes)
    return filename


def _cleanup_orphan_photos() -> None:
    """Borra fotos analizadas pero nunca confirmadas.

    /analyze guarda la imagen antes de que el usuario decida guardar el
    registro; sin esta limpieza uploads/ crece sin límite. Se preservan las
    referenciadas tanto por un registro como por una plantilla.
    """
    upload_dir = current_app.config['UPLOAD_FOLDER_ABS']
    max_age = current_app.config['ORPHAN_MAX_AGE_HOURS'] * 3600
    cutoff = time.time() - max_age

    try:
        entries = os.listdir(upload_dir)
    except OSError:
        return

    stale = []
    for name in entries:
        path = os.path.join(upload_dir, name)
        try:
            if os.path.isfile(path) and os.path.getmtime(path) < cutoff:
                stale.append(name)
        except OSError:
            continue

    if not stale:
        return

    referenced = {
        row[0] for row in
        db.session.query(FoodLog.photo_path).filter(FoodLog.photo_path.in_(stale)).all()
    }
    referenced |= {
        row[0] for row in
        db.session.query(FoodTemplate.photo_path).filter(FoodTemplate.photo_path.in_(stale)).all()
    }

    for name in stale:
        if name in referenced:
            continue
        try:
            os.remove(os.path.join(upload_dir, name))
        except OSError:
            current_app.logger.warning('No se pudo borrar la foto huerfana %s', name)


def _coerce_macro(value, field: str) -> float:
    """Convierte a float rechazando basura en lugar de reventar con un 500."""
    if value is None or value == '':
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field}" debe ser numérico.')
    if number != number or number in (float('inf'), float('-inf')):
        raise ValueError(f'El campo "{field}" no es un número válido.')
    return max(number, 0.0)


def _safe_filename(value) -> str | None:
    if value is None:
        return None
    name = os.path.basename(str(value))
    return name or None


def _parse_logged_at(value) -> datetime:
    """Momento de la ingesta, que puede no ser el de registro.

    El usuario a menudo apunta la comida más tarde, así que la app permite
    corregir fecha y hora. Sin offset se interpreta en la zona del usuario.
    """
    tz = _user_timezone()
    if not value:
        return datetime.now(tz)

    try:
        when = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError('Fecha y hora inválidas.')

    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)

    if when > datetime.now(tz) + timedelta(days=1):
        raise ValueError('No puedes registrar comidas con más de un día de antelación.')
    if when.year < 2000:
        raise ValueError('La fecha es demasiado antigua.')

    return when


# ─────────────────────────── análisis ───────────────────────────

@food_bp.route('/analyze', methods=['POST'])
def analyze():
    """Analiza una comida a partir de foto, descripción, o ambas.

    - foto sola          -> visión
    - foto + descripción -> visión, con la descripción como contexto
    - descripción sola   -> solo texto, sin coste de visión
    """
    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key or api_key.startswith('sk-ant-api03-REEMPLAZA'):
        return jsonify({'error': 'API key de Anthropic no configurada. Añade tu key en el archivo .env'}), 503

    payload = request.get_json(silent=True) if request.is_json else None
    description = (
        request.form.get('description')
        or request.form.get('context')
        or (payload or {}).get('description')
        or ''
    ).strip()[:1000]

    # 'photos' admite varias vistas del mismo plato; 'photo' se mantiene por
    # compatibilidad con clientes antiguos.
    files = [f for f in request.files.getlist('photos') if f and f.filename]
    if not files:
        files = [f for f in request.files.getlist('photo') if f and f.filename]

    if not files and not description:
        return jsonify({'error': 'Añade al menos una foto o una descripción'}), 400

    if len(files) > MAX_PHOTOS:
        return jsonify({'error': f'Máximo {MAX_PHOTOS} imágenes por comida'}), 400

    images: list[tuple[bytes, str]] = []
    for file in files:
        if not _allowed_file(file.filename):
            return jsonify({'error': f'Tipo de archivo no permitido: {file.filename}'}), 400
        try:
            images.append(normalize_image(
                file.read(),
                current_app.config['IMAGE_MAX_DIMENSION'],
                current_app.config['IMAGE_JPEG_QUALITY'],
            ))
        except UnsupportedImageError as exc:
            return jsonify({'error': str(exc)}), 400

    try:
        if images:
            analysis = analyze_food_images(images, description)
        else:
            analysis = analyze_food_text(description)
    except AnalysisError as exc:
        current_app.logger.error('Respuesta de Claude no interpretable: %s', exc)
        return jsonify({'error': 'No se pudo interpretar el análisis. Inténtalo de nuevo.'}), 502
    except Exception:
        current_app.logger.exception('Error llamando a la API de Anthropic')
        return jsonify({'error': 'Error al analizar. Inténtalo de nuevo.'}), 502

    analysis['source'] = 'photo' if images else 'text'
    # Se guardan todas, pero solo la primera representa la comida en las listas.
    filenames = [_save_normalized_image(b) for b, _ in images]
    analysis['photo_filenames'] = filenames
    analysis['photo_filename'] = filenames[0] if filenames else None
    return jsonify(analysis), 200


# ─────────────────────────── registro ───────────────────────────

def _legacy_to_items(data: dict) -> list[dict]:
    """Convierte el payload antiguo (una comida plana) en un único elemento."""
    return [{
        'name': data.get('description') or 'Comida',
        'quantity': '',
        'portion': 1,
        'components': data.get('foods_detected') or [],
        'photo_filename': data.get('photo_filename'),
        **{k: data.get(k) for k in MACRO_KEYS if k in data},
        'calories': data.get('total_calories', data.get('calories', 0)),
    }]


def _resolve_items(raw_items: list, meal_type: str, now: datetime) -> tuple[list[dict], str | None]:
    """Materializa los elementos de la comida y actualiza la biblioteca.

    Devuelve los elementos con macros ya escalados (snapshot para el registro)
    y la primera foto encontrada.
    """
    resolved = []
    photo = None

    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError('Elemento inválido en la lista.')

        try:
            portion = float(raw.get('portion', 1) or 1)
        except (TypeError, ValueError):
            raise ValueError('La porción debe ser numérica.')
        portion = min(max(portion, MIN_PORTION), MAX_PORTION)

        template = None
        template_id = raw.get('template_id')
        if isinstance(template_id, int):
            template = db.session.get(FoodTemplate, template_id)

        # Macros de referencia (1x): manda lo que envía el cliente, porque puede
        # haberlos corregido en la revisión; si no, los de la plantilla.
        provides_macros = any(k in raw for k in MACRO_KEYS)
        if provides_macros:
            base = {k: _coerce_macro(raw.get(k), k) for k in MACRO_KEYS}
        elif template:
            base = {k: getattr(template, k) for k in MACRO_KEYS}
        else:
            base = {k: 0.0 for k in MACRO_KEYS}

        name = str(raw.get('name') or (template.name if template else '')).strip()
        if not name:
            raise ValueError('Cada elemento necesita un nombre.')

        quantity = str(raw.get('quantity') or (template.quantity_label if template else ''))[:80]
        components = raw.get('components')
        if not isinstance(components, list):
            components = template.components if template else []

        item_photo = _safe_filename(raw.get('photo_filename'))
        if item_photo and not photo:
            photo = item_photo

        item_analysis = raw.get('analysis') if isinstance(raw.get('analysis'), dict) else None

        # La biblioteca se llena sola: si no venía de una plantilla, se crea.
        if template is None:
            template = library_service.upsert_template(
                name=name,
                macros=base,
                kind='dish' if components else 'food',
                quantity_label=quantity,
                components=components,
                photo_path=item_photo,
                source=str(raw.get('source') or 'ai'),
                analysis=item_analysis,
            )

        if template is not None:
            library_service.record_usage(template, meal_type, now)
            if item_photo and not template.photo_path:
                template.photo_path = item_photo

        resolved.append({
            'template_id': template.id if template else None,
            'name': name[:200],
            'quantity': quantity,
            'portion': round(portion, 2),
            'components': components,
            'analysis': item_analysis or (template.analysis if template else None) or {},
            **{k: round(base[k] * portion, 1) for k in MACRO_KEYS},
        })

    return resolved, photo


def _describe(items: list[dict]) -> str:
    names = [i['name'] for i in items]
    if len(names) == 1:
        return names[0]
    if len(names) <= 3:
        return ' + '.join(names)
    return f"{' + '.join(names[:2])} +{len(names) - 2} más"


@food_bp.route('/log', methods=['POST'])
def save_log():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    meal_type = str(data.get('meal_type', 'snack')).strip().lower()
    if meal_type not in VALID_MEAL_TYPES:
        return jsonify({'error': 'Tipo de comida no válido'}), 400

    confidence = str(data.get('confidence', 'medium')).strip().lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = 'medium'

    raw_items = data.get('items')
    if not isinstance(raw_items, list) or not raw_items:
        # Compatibilidad con el contrato anterior (una comida plana).
        raw_items = _legacy_to_items(data)

    if len(raw_items) > MAX_ITEMS:
        return jsonify({'error': f'Máximo {MAX_ITEMS} elementos por comida'}), 400

    try:
        when = _parse_logged_at(data.get('logged_at'))
        items, item_photo = _resolve_items(raw_items, meal_type, when)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    totals = {k: round(sum(i[k] for i in items), 1) for k in MACRO_KEYS}

    log = FoodLog(
        meal_type=meal_type,
        photo_path=_safe_filename(data.get('photo_filename')) or item_photo,
        description=str(data.get('description') or _describe(items))[:1000],
        foods_detected=[
            {'name': i['name'], 'quantity': i['quantity'], 'calories': round(i['calories'])}
            for i in items
        ],
        items=items,
        total_calories=totals['calories'],
        proteins=totals['proteins'],
        carbs=totals['carbs'],
        fats=totals['fats'],
        fiber=totals['fiber'],
        saturated_fat=totals['saturated_fat'],
        salt=totals['salt'],
        # Estimación de porciones y valoración: se conservan con el registro.
        analysis=data.get('analysis') if isinstance(data.get('analysis'), dict) else (
            items[0].get('analysis') if len(items) == 1 else None
        ),
        confidence=confidence,
        notes=str(data.get('notes', ''))[:1000],
        created_at=when,
    )
    db.session.add(log)
    db.session.commit()

    _cleanup_orphan_photos()

    return jsonify(log.to_dict()), 201


# ─────────────────────────── consultas ───────────────────────────

@food_bp.route('/logs', methods=['GET'])
def get_logs():
    page = max(request.args.get('page', 1, type=int), 1)
    per_page = min(max(request.args.get('per_page', 20, type=int), 1), 100)
    logs = FoodLog.query.order_by(FoodLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return jsonify({
        'items': [l.to_dict() for l in logs.items],
        'total': logs.total,
        'pages': logs.pages,
        'page': logs.page,
    })


def _daily_targets():
    """Objetivos diarios calculados desde el perfil, si ya hay datos."""
    profile = profile_service.get_or_create()
    return targets_service.compute(profile, profile_service.estimate_energy(profile))


def _day_payload(day: date) -> dict:
    day_start, day_end = _day_bounds(day)
    logs = (
        FoodLog.query.filter(FoodLog.created_at >= day_start, FoodLog.created_at < day_end)
        .order_by(FoodLog.created_at.asc())
        .all()
    )

    actividades = activity_service.for_day(day_start, day_end)
    gasto = energy_service.for_day(day)

    items = [l.to_dict() for l in logs]
    totals = {
        'calories': round(sum(l['total_calories'] for l in items), 1),
        'proteins': round(sum(l['proteins'] for l in items), 1),
        'carbs': round(sum(l['carbs'] for l in items), 1),
        'fats': round(sum(l['fats'] for l in items), 1),
        'fiber': round(sum(l['fiber'] for l in items), 1),
        'saturated_fat': round(sum(l['saturated_fat'] or 0 for l in items), 1),
        'salt': round(sum(l['salt'] or 0 for l in items), 1),
    }
    return {
        'date': day.isoformat(),
        'is_today': day == _local_today(),
        'items': items,
        'totals': totals,
        # Los objetivos viajan con el dia: la pantalla los necesita para pintar
        # el progreso y asi se evita una peticion aparte.
        'targets': _daily_targets(),
        'activities': [a.to_dict() for a in actividades],
        'activity_totals': activity_service.totals(actividades),
        # Gasto energético del día (manual hoy, Whoop en el futuro). Es un valor
        # único por día, no la suma de las actividades: se muestra junto a lo
        # consumido, pero NO se resta del objetivo (que ya incluye actividad).
        'energy': gasto.to_dict() if gasto else None,
    }


@food_bp.route('/logs/today', methods=['GET'])
def get_today_logs():
    return jsonify(_day_payload(_local_today()))


@food_bp.route('/logs/day', methods=['GET'])
def get_day_logs():
    """Comidas de un día concreto: /logs/day?date=2026-08-14"""
    try:
        day = _parse_date(request.args.get('date'), _local_today())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    return jsonify(_day_payload(day))


@food_bp.route('/summary', methods=['GET'])
def get_summary():
    """Totales agregados por día natural para un rango: /summary?from=&to=

    Se agrega en SQL convirtiendo a la zona del usuario. Traer todos los
    registros para sumarlos en Python no escala a una vista mensual.
    """
    today = _local_today()
    try:
        start_day = _parse_date(request.args.get('from'), today - timedelta(days=29))
        end_day = _parse_date(request.args.get('to'), today)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    if end_day < start_day:
        start_day, end_day = end_day, start_day

    span = (end_day - start_day).days + 1
    if span > 400:
        return jsonify({'error': 'El rango no puede superar 400 días'}), 400

    window_start, window_end = _day_bounds(start_day, span)
    tz_name = current_app.config['APP_TIMEZONE']

    rows = db.session.execute(
        text("""
            SELECT (created_at AT TIME ZONE :tz)::date AS day,
                   COUNT(*)                        AS meals,
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
        {'tz': tz_name, 'start': window_start, 'end': window_end},
    ).mappings().all()

    days = [
        {
            'date': row['day'].isoformat(),
            'meals': row['meals'],
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

    logged = [d for d in days if d['meals'] > 0]
    total_calories = sum(d['calories'] for d in logged)

    return jsonify({
        'targets': _daily_targets(),
        'activity_families': activity_service.FAMILIES,
        'activities_by_day': activity_service.families_by_day(
            window_start, window_end, current_app.config['APP_TIMEZONE']
        ),
        # Calorías gastadas por día natural, para pintarlas junto a las
        # consumidas en la rejilla del mes.
        'energy_by_day': energy_service.by_day(
            start_day, end_day, current_app.config['APP_TIMEZONE']
        ),
        'from': start_day.isoformat(),
        'to': end_day.isoformat(),
        'today': today.isoformat(),
        'days': days,
        'stats': {
            'days_logged': len(logged),
            'days_in_range': span,
            'total_calories': round(total_calories, 1),
            # La media se calcula solo sobre días con registros: incluir los
            # días vacíos como 0 kcal daría una media engañosa.
            'avg_calories': round(total_calories / len(logged), 1) if logged else 0,
            'best_day': max(logged, key=lambda d: d['calories'])['date'] if logged else None,
        },
    })


@food_bp.route('/logs/<int:log_id>', methods=['DELETE'])
def delete_log(log_id):
    log = db.session.get(FoodLog, log_id)
    if not log:
        return jsonify({'error': 'Registro no encontrado'}), 404

    # La foto puede estar compartida con una plantilla de la biblioteca.
    if log.photo_path:
        shared = FoodTemplate.query.filter_by(photo_path=log.photo_path).first()
        if not shared:
            photo = os.path.join(
                current_app.config['UPLOAD_FOLDER_ABS'], os.path.basename(log.photo_path)
            )
            try:
                os.remove(photo)
            except OSError:
                pass

    db.session.delete(log)
    db.session.commit()
    return jsonify({'message': 'Eliminado correctamente'})


@food_bp.route('/uploads/<filename>')
def serve_upload(filename):
    # send_from_directory ya bloquea el path traversal (safe_join).
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER_ABS'], filename, max_age=60 * 60 * 24 * 30
    )


@food_bp.route('/restore-upload', methods=['POST'])
def restore_upload():
    """Sube una foto conservando su nombre original, para restaurar en el volumen
    las imágenes de una migración. Doble candado: exige el token de la API (lo
    cubre el before_request) Y el flag ENABLE_PHOTO_RESTORE. Deja el flag sin
    poner (o bórralo) cuando termines la restauración; así queda inerte."""
    if os.environ.get('ENABLE_PHOTO_RESTORE', '').strip().lower() not in {'1', 'true', 'yes', 'on'}:
        return jsonify({'error': 'No disponible'}), 404

    file = request.files.get('file')
    if not file or not file.filename:
        return jsonify({'error': 'Falta el fichero'}), 400

    name = secure_filename(os.path.basename(file.filename))
    if not name or not name.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        return jsonify({'error': 'Nombre de fichero inválido'}), 400

    dest = os.path.join(current_app.config['UPLOAD_FOLDER_ABS'], name)
    file.save(dest)
    return jsonify({'ok': True, 'saved': name})
