"""Cliente OAuth de Whoop.

Cubre el flujo completo: consentimiento → callback → intercambio de código →
guardado y refresco del token, y la sincronización de workouts a la tabla
`activities` (`sync_recent_workouts()`). Se activa en cuanto haya
`WHOOP_CLIENT_ID`/`WHOOP_CLIENT_SECRET`; falta verificarlo contra la API real
con la pulsera conectada.

Whoop v2 (https://developer.whoop.com):
- Autorización:  GET  {AUTH_BASE}/oauth/oauth2/auth
- Token:         POST {AUTH_BASE}/oauth/oauth2/token   (code y refresh_token)
- API:           GET  {API_BASE}/v2/activity/workout, /v2/user/profile/basic ...

El `state` de OAuth es obligatorio (mín. 8 chars) y sirve de anti-CSRF: se
genera aquí y la ruta lo guarda en la sesión de Flask para comprobarlo al volver.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from flask import current_app

from .. import db
from ..models.activity import Activity
from ..models.whoop_token import WhoopToken
from . import activity_service, energy_service

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


# --- Paso 3: traer workouts y mapearlos a `activities` -----------------------

# Un joule -> kcal. Whoop da el gasto en kilojulios; se convierte a kcal, que es
# la unidad con la que trabaja el resto de la app.
_KJ_TO_KCAL = 1.0 / 4.184
_WORKOUT_PAGE = 25          # máximo por página que admite el endpoint
_MAX_PAGES = 20             # tope de seguridad para no pasear la API sin fin

# La v2 ya devuelve `sport_name` como texto; este mapa es solo una red por si un
# registro viniera sin él (se usa el id numérico). classify() hace el resto.
_SPORT_NAMES = {
    -1: 'Actividad', 0: 'Running', 1: 'Cycling', 16: 'Baseball',
    17: 'Basketball', 18: 'Rowing', 19: 'Fencing', 20: 'Field Hockey',
    21: 'Football', 22: 'Golf', 24: 'Ice Hockey', 25: 'Lacrosse',
    27: 'Rugby', 28: 'Sailing', 29: 'Skiing', 30: 'Soccer', 31: 'Softball',
    32: 'Squash', 33: 'Swimming', 34: 'Tennis', 35: 'Track & Field',
    36: 'Volleyball', 39: 'Boxing', 42: 'Dance', 43: 'Pilates', 44: 'Yoga',
    45: 'Weightlifting', 47: 'Functional Fitness', 48: 'Hiking',
    52: 'Spin', 62: 'HIIT', 63: 'Spinning', 66: 'Walking', 70: 'Meditation',
    71: 'Martial Arts', 96: 'Pickleball', 97: 'Padel', 101: 'Climbing',
}


def sync_recent_workouts(
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Trae los workouts de Whoop en la ventana [since, until) y los vuelca en
    `activities`.

    Sin argumentos sincroniza los últimos 30 días. Para un día concreto, pásale
    los límites de ese día (lo hace la ruta a partir de ?date=YYYY-MM-DD). El
    filtro es por el INICIO del workout, en la referencia horaria de Whoop (UTC).

    Idempotente: cada workout se identifica por su UUID en `external_id` (unique),
    así que reejecutar actualiza en vez de duplicar. Devuelve un resumen
    {created, updated, seen}.

    Recordatorio (CLAUDE.md): las calorías de Whoop son el gasto real del día y
    NO se restan del objetivo (ya incluye factor de actividad); son informativas.
    """
    token = valid_access_token()
    if token is None:
        raise WhoopError('Whoop no está conectado.')

    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=30)
    if until is None:
        until = datetime.now(timezone.utc)

    params = {
        'start': _iso(since),
        'end': _iso(until),
        'limit': _WORKOUT_PAGE,
    }

    created = updated = seen = 0
    with httpx.Client(base_url=API_BASE, timeout=_TIMEOUT) as client:
        next_token = None
        for _ in range(_MAX_PAGES):
            page_params = dict(params)
            if next_token:
                page_params['nextToken'] = next_token
            payload = _get(client, token, '/v2/activity/workout', page_params)

            for record in payload.get('records', []):
                seen += 1
                outcome = _upsert_workout(record)
                if outcome == 'created':
                    created += 1
                elif outcome == 'updated':
                    updated += 1

            next_token = payload.get('next_token')
            if not next_token:
                break

    if created or updated:
        db.session.commit()
    return {'created': created, 'updated': updated, 'seen': seen}


# --- Gasto energético total del día (ciclos de Whoop) ------------------------

def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo('UTC')


def sync_daily_energy(
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Trae el gasto energético TOTAL de cada día y lo vuelca en
    `energy_expenditures` (una fila por día natural, `source='whoop'`).

    El gasto del día entero vive en el *ciclo* fisiológico de Whoop
    (`/v2/cycle`, `score.kilojoule`), no en los workouts: los workouts son solo
    las sesiones. Cada ciclo se asigna al día natural de su inicio en la zona
    del usuario (`APP_TIMEZONE`).

    Sin argumentos sincroniza los últimos `WHOOP_SYNC_DAYS` días (7 por defecto),
    de modo que además de hoy repasa los días pasados por si alguno quedó sin
    dato. Respeta las correcciones manuales (ver `energy_service.record_whoop`).

    Devuelve {created, updated, skipped, seen}.
    """
    token = valid_access_token()
    if token is None:
        raise WhoopError('Whoop no está conectado.')

    days = int(current_app.config.get('WHOOP_SYNC_DAYS', 7) or 7)
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(days=days)
    if until is None:
        until = datetime.now(timezone.utc)

    tz = _local_tz()
    records = _fetch_cycles(token, since, until)

    # Un día puede tener más de un ciclo en la ventana; nos quedamos con el mayor
    # gasto de ese día (el ciclo completo, no un tramo parcial aún sin cerrar).
    per_day: dict = {}
    seen = 0
    for record in records:
        seen += 1
        start = _parse(record.get('start'))
        if start is None:
            continue
        # Solo el ciclo ya puntuado trae el gasto real del día; el ciclo en curso
        # (score_state != 'SCORED') da un total parcial que sería engañoso.
        if record.get('score_state') not in (None, 'SCORED'):
            continue
        kilojoule = (record.get('score') or {}).get('kilojoule')
        if kilojoule is None:
            continue
        day = start.astimezone(tz).date()
        kcal = round(kilojoule * _KJ_TO_KCAL, 1)
        per_day[day] = max(per_day.get(day, 0.0), kcal)

    created = updated = skipped = 0
    for day, kcal in per_day.items():
        outcome = energy_service.record_whoop(kcal, day)
        if outcome == 'created':
            created += 1
        elif outcome == 'updated':
            updated += 1
        elif outcome == 'skipped':
            skipped += 1

    if created or updated:
        db.session.commit()
    return {'created': created, 'updated': updated, 'skipped': skipped, 'seen': seen}


def _fetch_cycles(token: str, since: datetime, until: datetime) -> list:
    """Devuelve los registros crudos de ciclo de Whoop en [since, until)."""
    records: list = []
    params = {'start': _iso(since), 'end': _iso(until), 'limit': _WORKOUT_PAGE}
    with httpx.Client(base_url=API_BASE, timeout=_TIMEOUT) as client:
        next_token = None
        for _ in range(_MAX_PAGES):
            page_params = dict(params)
            if next_token:
                page_params['nextToken'] = next_token
            payload = _get(client, token, '/v2/cycle', page_params)
            records.extend(payload.get('records', []))
            next_token = payload.get('next_token')
            if not next_token:
                break
    return records


def debug_cycles(since: datetime, until: datetime) -> dict:
    """Diagnóstico: qué ciclos devuelve Whoop en una ventana, SIN escribir nada.

    Sirve para ver por qué el gasto de un día no cuadra con la app de Whoop
    (ciclo parcial, mapeo de día, kJ→kcal). Devuelve por ciclo su inicio/fin,
    estado de puntuación, kilojulios, kcal y a qué día natural se asignaría.
    """
    token = valid_access_token()
    if token is None:
        raise WhoopError('Whoop no está conectado.')

    tz = _local_tz()
    salida = []
    for record in _fetch_cycles(token, since, until):
        start = _parse(record.get('start'))
        score = record.get('score') or {}
        kilojoule = score.get('kilojoule')
        salida.append({
            'start': record.get('start'),
            'end': record.get('end'),
            'score_state': record.get('score_state'),
            'kilojoule': kilojoule,
            'kcal': round(kilojoule * _KJ_TO_KCAL, 1) if kilojoule is not None else None,
            'mapped_day': start.astimezone(tz).date().isoformat() if start else None,
        })
    return {
        'window': {'since': _iso(since), 'until': _iso(until)},
        'timezone': str(tz),
        'count': len(salida),
        'cycles': salida,
    }


def _upsert_workout(record: dict) -> str:
    """Crea o actualiza una `Activity` desde un workout de Whoop.

    Devuelve 'created', 'updated' o 'skipped' (registro sin datos utilizables).
    """
    external_id = record.get('id')
    start = _parse(record.get('start'))
    if not external_id or start is None:
        # started_at es NOT NULL y external_id es la clave de dedup: sin ellos el
        # registro no es utilizable, se ignora en vez de romper el commit.
        return 'skipped'

    activity = (
        db.session.query(Activity)
        .filter_by(external_id=str(external_id))
        .first()
    )
    is_new = activity is None
    if is_new:
        activity = Activity(source='whoop', external_id=str(external_id))
        db.session.add(activity)

    sport_name = record.get('sport_name') or _SPORT_NAMES.get(record.get('sport_id'), 'Entrenamiento')
    activity.sport_name = str(sport_name)[:120]
    activity.activity_type = activity_service.classify(activity.sport_name)

    end = _parse(record.get('end'))
    activity.started_at = start
    if end:
        activity.duration_min = max(0, round((end - start).total_seconds() / 60))

    score = record.get('score') or {}
    kilojoule = score.get('kilojoule')
    activity.calories = round(kilojoule * _KJ_TO_KCAL, 1) if kilojoule is not None else None

    # Lo exclusivo de la pulsera vive en metrics (no ensucia los registros manuales).
    activity.metrics = {
        'strain': score.get('strain'),
        'average_heart_rate': score.get('average_heart_rate'),
        'max_heart_rate': score.get('max_heart_rate'),
        'distance_meter': score.get('distance_meter'),
        'altitude_gain_meter': score.get('altitude_gain_meter'),
        'percent_recorded': score.get('percent_recorded'),
        'zone_durations': score.get('zone_duration') or score.get('zone_durations'),
        'score_state': record.get('score_state'),
    }
    return 'created' if is_new else 'updated'


def _get(client: httpx.Client, access_token: str, path: str, params: dict) -> dict:
    headers = {'Authorization': f'Bearer {access_token}'}
    try:
        resp = client.get(path, params=params, headers=headers)
    except httpx.HTTPError as exc:
        raise WhoopError(f'No se pudo contactar con Whoop: {exc}') from exc
    if resp.status_code == 401:
        raise WhoopError('Whoop rechazó el token (401); reconecta la cuenta.')
    if resp.status_code != 200:
        raise WhoopError(f'Whoop devolvió {resp.status_code}: {resp.text[:200]}')
    return resp.json()


def _iso(when: datetime) -> str:
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def _parse(value) -> datetime | None:
    """Parsea un timestamp ISO de Whoop (con 'Z' o fracciones) a datetime aware."""
    if not value:
        return None
    text = str(value).replace('Z', '+00:00')
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class WhoopError(Exception):
    """Fallo al hablar con Whoop (config ausente, token rechazado, red)."""
