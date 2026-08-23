from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..services import energy_service

energy_bp = Blueprint('energy', __name__)


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _local_today() -> date:
    return datetime.now(_tz()).date()


def _parse_date(value, fallback: date) -> date:
    if not value:
        return fallback
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise ValueError('Formato de fecha inválido, se espera YYYY-MM-DD.')


@energy_bp.route('/day', methods=['GET'])
def get_day():
    """Gasto de un día concreto: /day?date=2026-08-14. Devuelve null si no hay."""
    try:
        day = _parse_date(request.args.get('date'), _local_today())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    entry = energy_service.for_day(day)
    return jsonify({'entry': entry.to_dict() if entry else None})


@energy_bp.route('', methods=['POST'])
def create():
    """Registra (o corrige) el gasto de un día. Una entrada por día."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    try:
        day = _parse_date(data.get('measured_on') or data.get('date'), _local_today())
        note = data.get('note')
        entry = energy_service.record(
            data.get('calories'), day,
            source='manual',
            note=str(note)[:1000] if note is not None else None,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    return jsonify(entry.to_dict()), 201


@energy_bp.route('/<int:entry_id>', methods=['DELETE'])
def delete(entry_id):
    if not energy_service.delete(entry_id):
        return jsonify({'error': 'Registro no encontrado'}), 404
    db.session.commit()
    return jsonify({'message': 'Gasto eliminado'})
