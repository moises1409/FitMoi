"""Cliente OAuth de Whoop (esbozo).

Estado: la mecánica OAuth (consentimiento → callback → intercambio de código →
guardado y refresco del token) está implementada y lista para funcionar en
cuanto haya `WHOOP_CLIENT_ID`/`WHOOP_CLIENT_SECRET`. La SINCRONIZACIÓN de
workouts a la tabla `activities` queda esbozada en `sync_recent_workouts()`:
el mapeo de campos está anotado pero desactivado hasta poder probarlo con datos
reales de la pulsera (ver CLAUDE.md → "Pendiente: Integración con Whoop").

Whoop v2 (https://developer.whoop.com):
- Autorización:  GET  {AUTH_BASE}/oauth/oauth2/auth
- Token:         POST {AUTH_BASE}/oauth/oauth2/token   (code y refresh_token)
- API:           GET  {API_BASE}/v2/activity/workout, /v2/user/profile/basic ...

El `state` de OAuth es obligatorio (mín. 8 chars) y sirve de anti-CSRF: se
genera aquí y la ruta lo guarda en la sesión de Flask para comprobarlo al volver.
"""

from datetime import datetime, timedelta, timezone

import httpx
from flask import current_app

from .. import db
from ..models.whoop_token import WhoopToken

AUTH_BASE = 'https://api.prod.whoop.com'
API_BASE = 'https://api.prod.whoop.com/developer'
AUTHORIZE_URL = f'{AUTH_BASE}/oauth/oauth2/auth'
TOKEN_URL = f'{AUTH_BASE}/oauth/oauth2/token'

# `offline` es lo que hace que Whoop entregue refresh_token; sin él habría que
# reautorizar cada pocas horas. El resto son los permisos de lectura que usa la
# app (el gasto energético vive en workout/cycle).
DEFAULT_SCOPES = 'offline read:profile read:workout read:cycles read:recovery'

_TIMEOUT = httpx.Timeout(15.0)


# --- Configuración -----------------------------------------------------------

def is_configured() -> bool:
    """Hay Client ID/Secret: se puede intentar el flujo OAuth."""
    cfg = current_app.config
    return bool(cfg.get('WHOOP_CLIENT_ID') and cfg.get('WHOOP_CLIENT_SECRET'))


# --- Paso 1: URL de consentimiento -------------------------------------------

def authorize_url(state: str, redirect_uri: str) -> str:
    """URL a la que enviar al usuario para que autorice en Whoop."""
    params = {
        'response_type': 'code',
        'client_id': current_app.config['WHOOP_CLIENT_ID'],
        'redirect_uri': redirect_uri,
        'scope': current_app.config.get('WHOOP_SCOPES') or DEFAULT_SCOPES,
        'state': state,
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


# --- Paso 2: intercambio del código por tokens -------------------------------

def exchange_code(code: str, redirect_uri: str) -> WhoopToken:
    """Cambia el `code` del callback por access/refresh y lo persiste."""
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': current_app.config['WHOOP_CLIENT_ID'],
        'client_secret': current_app.config['WHOOP_CLIENT_SECRET'],
    }
    payload = _post_token(data)
    return _store(payload)


def refresh(token: WhoopToken) -> WhoopToken:
    """Renueva el access_token usando el refresh_token guardado."""
    if not token.refresh_token:
        raise WhoopError('No hay refresh_token; hay que reconectar Whoop.')
    data = {
        'grant_type': 'refresh_token',
        'refresh_token': token.refresh_token,
        'client_id': current_app.config['WHOOP_CLIENT_ID'],
        'client_secret': current_app.config['WHOOP_CLIENT_SECRET'],
        # Whoop exige repetir el scope 'offline' al refrescar para seguir
        # recibiendo un refresh_token nuevo.
        'scope': 'offline',
    }
    payload = _post_token(data)
    return _store(payload, existing=token)


def _post_token(data: dict) -> dict:
    try:
        resp = httpx.post(TOKEN_URL, data=data, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise WhoopError(f'No se pudo contactar con Whoop: {exc}') from exc
    if resp.status_code != 200:
        raise WhoopError(f'Whoop rechazó la petición de token ({resp.status_code}): {resp.text[:200]}')
    return resp.json()


# --- Persistencia (una sola fila: app de usuario único) ----------------------

def current_token() -> WhoopToken | None:
    return db.session.query(WhoopToken).order_by(WhoopToken.id.asc()).first()


def valid_access_token() -> str | None:
    """Access token utilizable, refrescándolo si hace falta. None si no hay conexión."""
    token = current_token()
    if token is None:
        return None
    if token.is_expired():
        token = refresh(token)
    return token.access_token


def is_connected() -> bool:
    return current_token() is not None


def disconnect() -> None:
    """Olvida las credenciales locales (no revoca en Whoop; eso lo hace el usuario)."""
    for token in db.session.query(WhoopToken).all():
        db.session.delete(token)
    db.session.commit()


def _store(payload: dict, existing: WhoopToken | None = None) -> WhoopToken:
    token = existing or current_token() or WhoopToken()
    token.access_token = payload['access_token']
    # En un refresh Whoop devuelve un refresh_token nuevo; si no viene, se conserva.
    if payload.get('refresh_token'):
        token.refresh_token = payload['refresh_token']
    token.scope = payload.get('scope') or token.scope
    expires_in = int(payload.get('expires_in', 3600))
    token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if token.id is None:
        db.session.add(token)
    db.session.commit()
    return token


# --- Paso 3 (esbozo): traer workouts y mapearlos a `activities` ---------------

def sync_recent_workouts() -> int:
    """PENDIENTE. Trae los workouts recientes y los vuelca en `activities`.

    La tabla `activities` ya tiene las columnas para esto (source='whoop',
    external_id=UUID del workout, calories, metrics con strain/pulso/zonas). El
    mapeo sería, por cada workout de GET {API_BASE}/v2/activity/workout:

        Activity(
            source='whoop',
            external_id=w['id'],                     # dedup por unique
            sport_name=<nombre del sport_id>,
            activity_type=activity_service.family_of(...),
            started_at=parse(w['start']),
            duration_min=(parse(w['end']) - parse(w['start'])).minutes,
            calories=w['score']['kilojoule'] / 4.184, # kJ -> kcal
            metrics={strain, average_heart_rate, max_heart_rate, zone_durations},
        )

    Recordatorio (CLAUDE.md): las calorías de Whoop son el gasto real del día;
    NO se restan del objetivo (ya incluye factor de actividad). Se deja
    desactivado hasta poder probarlo con la pulsera conectada.
    """
    raise NotImplementedError('Sincronización de workouts pendiente (fase 2).')


class WhoopError(Exception):
    """Fallo al hablar con Whoop (config ausente, token rechazado, red)."""
