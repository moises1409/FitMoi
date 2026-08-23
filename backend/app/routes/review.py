"""Resumen semanal de nutrición y actividad.

La generación es perezosa: `GET /weekly` de una semana ya cerrada la calcula, la
redacta con el LLM y la guarda; las siguientes lecturas la sirven de la BD. La
semana en curso se devuelve como vista previa (cifras vivas, sin narrativa).
`POST /weekly/regenerate` fuerza el recálculo.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..services import weekly_review_service
from ..services.claude_service import AnalysisError

review_bp = Blueprint('review', __name__)


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


@review_bp.route('/weekly', methods=['GET'])
def get_weekly():
    """Resumen de la semana que contiene ?date=YYYY-MM-DD (por defecto, hoy)."""
    try:
        anchor = _parse_date(request.args.get('date'), _local_today())
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    return jsonify(weekly_review_service.weekly_payload(anchor))


@review_bp.route('/weekly/list', methods=['GET'])
def list_weekly():
    """Resúmenes guardados, del más reciente al más antiguo."""
    limit = min(max(request.args.get('limit', 26, type=int), 1), 104)
    return jsonify({'items': weekly_review_service.list_reviews(limit)})


@review_bp.route('/weekly/regenerate', methods=['POST'])
def regenerate_weekly():
    """Fuerza el recálculo y la reescritura de una semana."""
    data = request.get_json(silent=True) or {}
    try:
        anchor = _parse_date(data.get('date') or request.args.get('date'), _local_today())
        payload = weekly_review_service.regenerate(anchor)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except AnalysisError as exc:
        db.session.rollback()
        current_app.logger.error('Error redactando el resumen semanal: %s', exc)
        return jsonify({'error': 'No se pudo generar el resumen. Inténtalo de nuevo.'}), 502

    return jsonify(payload)
