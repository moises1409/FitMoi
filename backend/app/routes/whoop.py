"""Rutas OAuth de Whoop (esbozo).

Flujo:
  GET /api/whoop/authorize  -> genera state, redirige al consentimiento de Whoop
  GET /api/whoop/callback   -> Whoop devuelve aquí con ?code&state; se intercambia
  GET /api/whoop/status     -> ¿configurado?, ¿conectado? (lo consulta el frontend)
  POST /api/whoop/disconnect-> olvida el token local

La redirect URL registrada en el portal de Whoop debe ser exactamente:
    https://TU-DOMINIO/api/whoop/callback   (y http://localhost:5000/... en dev)

Estas rutas viven bajo /api/ y por tanto las cubre el candado (app/auth.py). El
callback es una navegación GET de nivel superior, así que la cookie del candado
(SameSite=Lax) viaja de vuelta y solo el usuario ya autenticado puede completar
la conexión: es justo lo que queremos.
"""

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Blueprint, current_app, jsonify, redirect, request, session, url_for,
)

from ..services import whoop_service
from ..services.whoop_service import WhoopError

whoop_bp = Blueprint('whoop', __name__)

_STATE_KEY = 'whoop_oauth_state'
# A dónde volver en el SPA tras conectar (mismo origen en producción).
_FRONTEND_RETURN = '/activity'


def _callback_uri() -> str:
    """URI de callback. Fija por config si se define; si no, se deriva de la
    petición (vale en local y en producción sin tocar variables), pero debe
    COINCIDIR con la registrada en Whoop."""
    configured = current_app.config.get('WHOOP_REDIRECT_URI', '') or ''
    if configured:
        return configured
    return url_for('whoop.callback', _external=True)


@whoop_bp.route('/status', methods=['GET'])
def status():
    return jsonify({
        'configured': whoop_service.is_configured(),
        'connected': whoop_service.is_connected(),
    })


@whoop_bp.route('/authorize', methods=['GET'])
def authorize():
    if not whoop_service.is_configured():
        return jsonify({'error': 'Whoop no está configurado en el servidor.'}), 503

    state = secrets.token_urlsafe(24)  # > 8 chars, anti-CSRF
    session[_STATE_KEY] = state
    return redirect(whoop_service.authorize_url(state, _callback_uri()))


@whoop_bp.route('/callback', methods=['GET'])
def callback():
    error = request.args.get('error')
    if error:
        return _fail(f'Whoop denegó la autorización: {error}')

    code = request.args.get('code')
    state = request.args.get('state')
    expected = session.pop(_STATE_KEY, None)
    if not code or not state or state != expected:
        return _fail('Estado OAuth inválido; vuelve a intentar la conexión.')

    try:
        whoop_service.exchange_code(code, _callback_uri())
    except WhoopError as exc:
        return _fail(str(exc))

    return redirect(f'{_FRONTEND_RETURN}?whoop=connected')


@whoop_bp.route('/sync', methods=['POST'])
def sync():
    """Trae de Whoop los workouts (a `activities`) y el gasto total del día
    (a `energy_expenditures`).

    Sin parámetros sincroniza una ventana reciente. Con ?date=YYYY-MM-DD (o en el
    cuerpo JSON) sincroniza solo ese día natural, en la zona horaria del usuario.
    Idempotente; devuelve created/updated/seen de los workouts y, en `energy`, el
    resultado del gasto diario.
    """
    if not whoop_service.is_connected():
        return jsonify({'error': 'Whoop no está conectado.'}), 409

    data = request.get_json(silent=True) or {}
    date_str = request.args.get('date') or data.get('date')
    since = until = None
    if date_str:
        try:
            since, until = _day_bounds(str(date_str))
        except ValueError:
            return jsonify({'error': 'Fecha inválida; usa YYYY-MM-DD.'}), 400

    try:
        result = whoop_service.sync_recent_workouts(since=since, until=until)
        result['energy'] = whoop_service.sync_daily_energy(since=since, until=until)
    except WhoopError as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify(result)


def _day_bounds(date_str: str):
    """Límites [inicio, fin) de un día natural YYYY-MM-DD en la zona del usuario."""
    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('Fecha inválida')
    try:
        tz = ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo('UTC')
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


@whoop_bp.route('/disconnect', methods=['POST'])
def disconnect():
    whoop_service.disconnect()
    return jsonify({'ok': True})


def _fail(message: str):
    """Vuelve al SPA con el motivo en la query para que la UI lo muestre."""
    return redirect(f'{_FRONTEND_RETURN}?whoop=error&reason={message}')
