"""Rutas OAuth de Withings + sincronización de la báscula.

Flujo:
  GET  /api/withings/authorize  -> genera state, redirige al consentimiento
  GET  /api/withings/callback   -> Withings vuelve aquí con ?code&state; se cambia
  GET  /api/withings/status     -> ¿configurado?, ¿conectado? (lo consulta el frontend)
  POST /api/withings/sync       -> trae las mediciones al histórico de peso
  POST /api/withings/disconnect -> olvida el token local

La redirect URL registrada en el portal de Withings debe ser exactamente:
    https://TU-DOMINIO/api/withings/callback   (y http://localhost:5000/... en dev)

Estas rutas viven bajo /api/ y por tanto las cubre el candado (app/auth.py). El
callback es una navegación GET de nivel superior, así que la cookie del candado
(SameSite=Lax) viaja de vuelta y solo el usuario ya autenticado puede completar
la conexión (mismo patrón que Whoop).
"""

import secrets
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from flask import (
    Blueprint, current_app, jsonify, redirect, request, url_for,
)

from ..services import oauth_state_service, withings_service
from ..services.withings_service import WithingsError

withings_bp = Blueprint('withings', __name__)

_PROVIDER = 'withings'
# A dónde volver en el SPA tras conectar (mismo origen en producción).
_FRONTEND_RETURN = '/profile'


def _callback_uri() -> str:
    """URI de callback. Fija por config si se define; si no, se deriva de la
    petición (vale en local y en producción sin tocar variables), pero debe
    COINCIDIR con la registrada en Withings."""
    configured = current_app.config.get('WITHINGS_REDIRECT_URI', '') or ''
    if configured:
        return configured
    return url_for('withings.callback', _external=True)


@withings_bp.route('/status', methods=['GET'])
def status():
    return jsonify({
        'configured': withings_service.is_configured(),
        'connected': withings_service.is_connected(),
    })


@withings_bp.route('/authorize', methods=['GET'])
def authorize():
    if not withings_service.is_configured():
        return jsonify({'error': 'Withings no está configurado en el servidor.'}), 503

    state = secrets.token_urlsafe(24)  # anti-CSRF
    oauth_state_service.issue(_PROVIDER, state)
    return redirect(withings_service.authorize_url(state, _callback_uri()))


@withings_bp.route('/callback', methods=['GET'])
def callback():
    error = request.args.get('error')
    if error:
        return _fail(f'Withings denegó la autorización: {error}')

    code = request.args.get('code')
    state = request.args.get('state')
    if not code or not oauth_state_service.consume(_PROVIDER, state):
        return _fail('Estado OAuth inválido; vuelve a intentar la conexión.')

    try:
        withings_service.exchange_code(code, _callback_uri())
        # Primera sincronización nada más conectar, para que la báscula aparezca ya.
        withings_service.sync_measurements()
    except WithingsError as exc:
        return _fail(str(exc))

    return redirect(f'{_FRONTEND_RETURN}?withings=connected')


@withings_bp.route('/sync', methods=['POST'])
def sync():
    """Trae de Withings las mediciones de la báscula al histórico de peso.

    Sin parámetros sincroniza una ventana reciente (WITHINGS_SYNC_DAYS días). Con
    ?date=YYYY-MM-DD (o en el cuerpo JSON) sincroniza solo ese día natural, en la
    zona horaria del usuario. Idempotente; devuelve created/updated/skipped/seen.
    """
    if not withings_service.is_connected():
        return jsonify({'error': 'Withings no está conectado.'}), 409

    data = request.get_json(silent=True) or {}
    date_str = request.args.get('date') or data.get('date')
    since = until = None
    if date_str:
        try:
            since, until = _day_bounds(str(date_str))
        except ValueError:
            return jsonify({'error': 'Fecha inválida; usa YYYY-MM-DD.'}), 400

    try:
        result = withings_service.sync_measurements(since=since, until=until)
    except WithingsError as exc:
        return jsonify({'error': str(exc)}), 502
    return jsonify(result)


@withings_bp.route('/measures', methods=['GET'])
def measures_debug():
    """Diagnóstico (solo lectura): qué mediciones devuelve Withings.

    GET /api/withings/measures?date=YYYY-MM-DD → ese día (o los últimos 7 sin
    fecha), con cada grupo, su día natural y los valores ya escalados. No escribe.
    """
    if not withings_service.is_connected():
        return jsonify({'error': 'Withings no está conectado.'}), 409

    date_str = request.args.get('date')
    try:
        if date_str:
            since, until = _day_bounds(str(date_str))
        else:
            until = datetime.now(_tz())
            since = until - timedelta(days=7)
    except ValueError:
        return jsonify({'error': 'Fecha inválida; usa YYYY-MM-DD.'}), 400

    try:
        return jsonify(withings_service.debug_measures(since, until))
    except WithingsError as exc:
        return jsonify({'error': str(exc)}), 502


@withings_bp.route('/disconnect', methods=['POST'])
def disconnect():
    withings_service.disconnect()
    return jsonify({'ok': True})


def _tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('UTC')


def _day_bounds(date_str: str):
    """Límites [inicio, fin) de un día natural YYYY-MM-DD en la zona del usuario."""
    try:
        day = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        raise ValueError('Fecha inválida')
    tz = _tz()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    return start, start + timedelta(days=1)


def _fail(message: str):
    """Vuelve al SPA con el motivo en la query para que la UI lo muestre."""
    return redirect(f'{_FRONTEND_RETURN}?withings=error&reason={message}')
