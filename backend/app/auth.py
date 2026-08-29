"""Candado de acceso de un solo secreto para toda la API.

La app es de usuario único: no hay tabla de usuarios ni contraseñas, solo un
token compartido (`APP_ACCESS_TOKEN`). Si esa variable está vacía el candado
queda DESACTIVADO —así el desarrollo local sigue funcionando sin tocar nada— y
solo se activa cuando se define el token (p. ej. en producción/Railway).

Se valida por COOKIE, no por cabecera, a propósito: las fotos se cargan con
`<img src="/api/food/uploads/...">` y una etiqueta `<img>` no puede mandar una
cabecera `Authorization`, pero sí envía la cookie sola. Se acepta además un
`Bearer` en cabecera para clientes que no sean el navegador (curl, scripts).
"""

import hmac

from flask import Blueprint, current_app, jsonify, request

auth_bp = Blueprint('auth', __name__)

COOKIE_NAME = 'fitmoi_auth'
COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # un año
# El propio candado y el chequeo de salud nunca se protegen. Los callbacks de
# OAuth tampoco: son una vuelta de una navegación CROSS-SITE (Withings/Whoop ->
# app) y la cookie del candado (SameSite=Lax) no viaja en ese salto, así que
# exigirla daría un 401 al volver de autorizar. No hace falta: el callback ya lo
# protege el `state` de OAuth (anti-CSRF) y el flujo solo puede arrancarlo un
# usuario autenticado desde `/authorize`, que SÍ está tras el candado.
OPEN_PATHS = {'/health', '/api/withings/callback', '/api/whoop/callback'}
OPEN_PREFIX = '/api/auth/'


def _configured_token() -> str:
    return current_app.config.get('APP_ACCESS_TOKEN', '') or ''


def _supplied_token() -> str:
    """Token que trae la petición: primero la cookie, luego `Bearer` en cabecera."""
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie:
        return cookie
    header = request.headers.get('Authorization', '')
    if header.startswith('Bearer '):
        return header[7:]
    return ''


def _matches(supplied: str, token: str) -> bool:
    # compare_digest evita filtrar el token por tiempos de comparación.
    return bool(supplied) and hmac.compare_digest(supplied, token)


def _set_cookie(response):
    response.set_cookie(
        COOKIE_NAME,
        _configured_token(),
        max_age=COOKIE_MAX_AGE,
        httponly=True,               # el JavaScript del navegador no puede leerla
        samesite='Lax',
        secure=current_app.config.get('COOKIE_SECURE', False),  # True en producción (HTTPS)
        path='/',
    )
    return response


def init_auth(app):
    """Registra el guardián y el blueprint de login sobre la app."""

    @app.before_request
    def _guard():
        token = _configured_token()
        if not token:
            return None  # candado desactivado

        path = request.path
        if request.method == 'OPTIONS':
            return None  # preflight de CORS
        if path in OPEN_PATHS or path.startswith(OPEN_PREFIX):
            return None
        if not path.startswith('/api/'):
            return None  # solo se protege la API

        if not _matches(_supplied_token(), token):
            return jsonify({'error': 'No autorizado'}), 401
        return None

    app.register_blueprint(auth_bp, url_prefix='/api/auth')


@auth_bp.route('/status', methods=['GET'])
def status():
    """Dice si hace falta candado y si esta petición ya está autenticada.
    Lo consulta el frontend al arrancar para decidir si mostrar el login."""
    token = _configured_token()
    if not token:
        return jsonify({'required': False, 'authed': True})
    return jsonify({'required': True, 'authed': _matches(_supplied_token(), token)})


@auth_bp.route('/login', methods=['POST'])
def login():
    token = _configured_token()
    if not token:
        # No hay nada que desbloquear; se responde ok para que el frontend siga.
        return jsonify({'ok': True, 'required': False})

    data = request.get_json(silent=True) or {}
    if not _matches(str(data.get('token', '')), token):
        return jsonify({'error': 'Token incorrecto'}), 401

    return _set_cookie(jsonify({'ok': True}))


@auth_bp.route('/logout', methods=['POST'])
def logout():
    response = jsonify({'ok': True})
    response.delete_cookie(COOKIE_NAME, path='/')
    return response
