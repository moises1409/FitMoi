from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..models.activity import Activity
from ..services import activity_service

activity_bp = Blueprint('activity', __name__)

MAX_DURATION_MIN = 24 * 60
MAX_CALORIES = 10000


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _parse_started_at(value) -> datetime:
    """Momento de la sesión. Sin offset se interpreta en la zona del usuario."""
    tz = _tz()
    if not value:
        return datetime.now(tz)
    try:
        when = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError('Fecha y hora inválidas.')
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    if when > datetime.now(tz) + timedelta(days=1):
        raise ValueError('No puedes registrar una actividad futura.')
    return when


def _number(value, field: str, maximum: float):
    if value in (None, ''):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field}" debe ser numérico.')
    if number < 0 or number > maximum:
        raise ValueError(f'El campo "{field}" está fuera de rango.')
    return number


def _apply(activity: Activity, data: dict) -> None:
    sport = str(data.get('sport_name', '')).strip()[:120]
    if not sport:
        raise ValueError('Dinos qué actividad has hecho.')

    activity.sport_name = sport
    activity.activity_type = activity_service.family_of(
        str(data.get('activity_type', '')).strip(), sport
    )
    activity.started_at = _parse_started_at(data.get('started_at'))

    duracion = _number(data.get('duration_min'), 'duration_min', MAX_DURATION_MIN)
    activity.duration_min = int(duracion) if duracion is not None else None
    activity.calories = _number(data.get('calories'), 'calories', MAX_CALORIES)

    sensacion = data.get('feeling')
    if sensacion in (None, ''):
        activity.feeling = None
    else:
        try:
            valor = int(sensacion)
        except (TypeError, ValueError):
            raise ValueError('La sensación debe ser un número del 1 al 5.')
        if not 1 <= valor <= 5:
            raise ValueError('La sensación debe estar entre 1 y 5.')
        activity.feeling = valor

    activity.notes = str(data.get('notes', ''))[:1000] or None


@activity_bp.route('/families', methods=['GET'])
def families():
    """Familias con su color: las usa el calendario para la leyenda."""
    return jsonify({'families': activity_service.FAMILIES})


@activity_bp.route('', methods=['POST'])
def create():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    activity = Activity(source='manual')
    try:
        _apply(activity, data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    db.session.add(activity)
    db.session.commit()
    return jsonify(activity.to_dict()), 201


@activity_bp.route('/<int:activity_id>', methods=['GET'])
def get_one(activity_id):
    """Una actividad suelta: la carga el formulario al editarla."""
    activity = db.session.get(Activity, activity_id)
    if not activity:
        return jsonify({'error': 'Actividad no encontrada'}), 404
    return jsonify(activity.to_dict())


@activity_bp.route('/<int:activity_id>', methods=['PATCH'])
def update(activity_id):
    activity = db.session.get(Activity, activity_id)
    if not activity:
        return jsonify({'error': 'Actividad no encontrada'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    # Lo que sincroniza la pulsera no se edita a mano: se resincronizaría encima.
    if activity.source != 'manual':
        return jsonify({'error': 'Esta actividad viene de Whoop y no se edita aquí'}), 409

    combinado = {**activity.to_dict(), **data}
    try:
        _apply(activity, combinado)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    return jsonify(activity.to_dict())


@activity_bp.route('/<int:activity_id>', methods=['DELETE'])
def delete(activity_id):
    activity = db.session.get(Activity, activity_id)
    if not activity:
        return jsonify({'error': 'Actividad no encontrada'}), 404

    db.session.delete(activity)
    db.session.commit()
    return jsonify({'message': 'Actividad eliminada'})
