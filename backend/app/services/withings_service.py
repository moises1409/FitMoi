"""Cliente OAuth de Withings + sincronización de la báscula.

Trae del API de Withings las mediciones de la báscula inteligente (peso y
composición corporal: grasa, músculo, hueso, agua) y las guarda en el histórico
de peso (`weight_entries`), una fila por día natural. Se activa en cuanto haya
`WITHINGS_CLIENT_ID`/`WITHINGS_CLIENT_SECRET`; falta verificarlo contra el API
real con la báscula conectada.

Withings (https://developer.withings.com):
- Autorización:  GET  https://account.withings.com/oauth2_user/authorize2
- Token:         POST https://wbsapi.withings.net/v2/oauth2  (action=requesttoken)
- Mediciones:    POST https://wbsapi.withings.net/measure    (action=getmeas)

Dos rarezas de Withings frente a un OAuth clásico (por eso no se reusa el de
Whoop):
- El token y todas las llamadas al API van con un parámetro `action` en el
  cuerpo, y la respuesta viene ENVUELTA en `{status, body}`: `status != 0` es
  un error aunque el HTTP sea 200.
- Las medidas llegan como enteros con un exponente: el valor real es
  `value * 10**unit` (p. ej. value=6850, unit=-2 → 68.50 kg).

El `state` de OAuth es anti-CSRF: se genera aquí y la ruta lo guarda en la
sesión de Flask para comprobarlo al volver.
"""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from flask import current_app

from .. import db
from ..models.weight_entry import WeightEntry
from ..models.withings_token import WithingsToken
from . import profile_service, weight_service

AUTHORIZE_URL = 'https://account.withings.com/oauth2_user/authorize2'
TOKEN_URL = 'https://wbsapi.withings.net/v2/oauth2'
MEASURE_URL = 'https://wbsapi.withings.net/measure'

# `user.metrics` da acceso a las mediciones de la báscula. Es el único scope que
# necesita la app; se puede sobreescribir con WITHINGS_SCOPES.
DEFAULT_SCOPES = 'user.metrics'

_TIMEOUT = httpx.Timeout(20.0)

# Tipos de medida de Withings que interesan y a qué columna van. La grasa (6) es
# ya un porcentaje; el resto son masas en kg (el % lo deriva la vista). El peso
# (1) es obligatorio: sin él el grupo no es una pesada utilizable.
_MEASURE_TYPES = {
    1: 'weight_kg',
    6: 'fat_ratio',
    8: 'fat_mass_kg',
    76: 'muscle_mass_kg',
    77: 'hydration_kg',
    88: 'bone_mass_kg',
}
_MEASTYPES_PARAM = ','.join(str(t) for t in _MEASURE_TYPES)


# --- Configuración -----------------------------------------------------------

def is_configured() -> bool:
    """Hay Client ID/Secret: se puede intentar el flujo OAuth."""
    cfg = current_app.config
    return bool(cfg.get('WITHINGS_CLIENT_ID') and cfg.get('WITHINGS_CLIENT_SECRET'))


# --- Paso 1: URL de consentimiento -------------------------------------------

def authorize_url(state: str, redirect_uri: str) -> str:
    """URL a la que enviar al usuario para que autorice en Withings."""
    params = {
        'response_type': 'code',
        'client_id': current_app.config['WITHINGS_CLIENT_ID'],
        'redirect_uri': redirect_uri,
        'scope': current_app.config.get('WITHINGS_SCOPES') or DEFAULT_SCOPES,
        'state': state,
    }
    return str(httpx.URL(AUTHORIZE_URL, params=params))


# --- Paso 2: intercambio del código por tokens -------------------------------

def exchange_code(code: str, redirect_uri: str) -> WithingsToken:
    """Cambia el `code` del callback por access/refresh y lo persiste."""
    data = {
        'action': 'requesttoken',
        'grant_type': 'authorization_code',
        'client_id': current_app.config['WITHINGS_CLIENT_ID'],
        'client_secret': current_app.config['WITHINGS_CLIENT_SECRET'],
        'code': code,
        'redirect_uri': redirect_uri,
    }
    payload = _post_token(data)
    return _store(payload)


def refresh(token: WithingsToken) -> WithingsToken:
    """Renueva el access_token usando el refresh_token guardado."""
    if not token.refresh_token:
        raise WithingsError('No hay refresh_token; hay que reconectar Withings.')
    data = {
        'action': 'requesttoken',
        'grant_type': 'refresh_token',
        'client_id': current_app.config['WITHINGS_CLIENT_ID'],
        'client_secret': current_app.config['WITHINGS_CLIENT_SECRET'],
        'refresh_token': token.refresh_token,
    }
    payload = _post_token(data)
    return _store(payload, existing=token)


def _post_token(data: dict) -> dict:
    """POST al endpoint de token y devuelve el `body` ya desenvuelto.

    Withings envuelve la respuesta en `{status, body}`: status != 0 es un error
    (código de app), aunque el HTTP sea 200.
    """
    try:
        resp = httpx.post(TOKEN_URL, data=data, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise WithingsError(f'No se pudo contactar con Withings: {exc}') from exc
    if resp.status_code != 200:
        raise WithingsError(
            f'Withings rechazó la petición de token ({resp.status_code}): {resp.text[:200]}'
        )
    try:
        wrapper = resp.json()
    except ValueError as exc:
        raise WithingsError('Withings devolvió una respuesta no interpretable.') from exc
    status = wrapper.get('status')
    if status != 0:
        raise WithingsError(f'Withings rechazó el token (status {status}): {str(wrapper)[:200]}')
    return wrapper.get('body') or {}


# --- Persistencia (una sola fila: app de usuario único) ----------------------

def current_token() -> WithingsToken | None:
    return db.session.query(WithingsToken).order_by(WithingsToken.id.asc()).first()


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
    """Olvida las credenciales locales (no revoca en Withings; eso lo hace el usuario)."""
    for token in db.session.query(WithingsToken).all():
        db.session.delete(token)
    db.session.commit()


def _store(payload: dict, existing: WithingsToken | None = None) -> WithingsToken:
    if not payload.get('access_token'):
        raise WithingsError('Withings no devolvió un access_token.')
    token = existing or current_token() or WithingsToken()
    token.access_token = payload['access_token']
    # En un refresh Withings devuelve un refresh_token nuevo; si no viene, se conserva.
    if payload.get('refresh_token'):
        token.refresh_token = payload['refresh_token']
    token.scope = payload.get('scope') or token.scope
    userid = payload.get('userid')
    if userid is not None:
        token.withings_user_id = str(userid)
    expires_in = int(payload.get('expires_in', 3600))
    token.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    if token.id is None:
        db.session.add(token)
    db.session.commit()
    return token


# --- Paso 3: traer mediciones y volcarlas al histórico de peso ---------------

def _local_tz() -> ZoneInfo:
    try:
        return ZoneInfo(current_app.config['APP_TIMEZONE'])
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        return ZoneInfo('UTC')


def sync_measurements(
    since: datetime | None = None,
    until: datetime | None = None,
) -> dict:
    """Trae las mediciones de la báscula en [since, until) y las vuelca en
    `weight_entries` (una fila por día natural, `source='withings'`).

    Sin argumentos sincroniza una ventana reciente (`WITHINGS_SYNC_DAYS`), salvo
    la PRIMERA vez —cuando aún no hay ninguna pesada de la báscula—, en la que se
    trae una ventana AMPLIA (`WITHINGS_INITIAL_SYNC_DAYS`, un año por defecto)
    para rellenar de golpe el histórico de peso y composición. Para un día
    concreto, pásale los límites de ese día (lo hace la ruta a partir de
    ?date=YYYY-MM-DD). Cada grupo de medida se asigna al día natural de su fecha
    en la zona del usuario (`APP_TIMEZONE`); si un día tiene varias pesadas se
    conserva la más reciente.

    Idempotente (una fila por día). Respeta una corrección manual del peso: un
    día con `source='manual'` no se pisa. Devuelve {created, updated, skipped, seen}.
    """
    token = valid_access_token()
    if token is None:
        raise WithingsError('Withings no está conectado.')

    if since is None:
        # La primera sincronización (aún sin datos de la báscula) barre una
        # ventana amplia para traer todo el histórico; luego, ventana corta.
        ya_hay = db.session.query(WeightEntry.id).filter_by(source='withings').first() is not None
        clave = 'WITHINGS_SYNC_DAYS' if ya_hay else 'WITHINGS_INITIAL_SYNC_DAYS'
        por_defecto = 30 if ya_hay else 365
        days = int(current_app.config.get(clave, por_defecto) or por_defecto)
        since = datetime.now(timezone.utc) - timedelta(days=days)
    if until is None:
        until = datetime.now(timezone.utc)

    tz = _local_tz()
    groups = _fetch_measure_groups(token, since, until)

    # Un día puede tener varias pesadas; nos quedamos con la más reciente (mayor
    # timestamp) para no perder la composición si una lectura vino incompleta.
    best_per_day: dict = {}
    seen = 0
    for group in groups:
        ts = group.get('date')
        if ts is None:
            continue
        seen += 1
        when = datetime.fromtimestamp(int(ts), tz)
        # El API filtra por rango, pero por si acaso reconfirmamos la ventana.
        if not (since <= when.astimezone(timezone.utc) < until):
            continue
        day = when.date()
        prev = best_per_day.get(day)
        if prev is None or int(ts) > prev[0]:
            best_per_day[day] = (int(ts), _parse_measures(group.get('measures') or []))

    profile = profile_service.get_or_create()
    created = updated = skipped = 0
    for day, (_, values) in best_per_day.items():
        weight = values.get('weight_kg')
        if weight is None:
            # Sin peso no es una pesada utilizable (p. ej. solo una lectura suelta).
            continue
        composition = {k: v for k, v in values.items() if k != 'weight_kg'}
        outcome = weight_service.record_withings(profile, weight, when=day,
                                                 composition=composition)
        if outcome == 'created':
            created += 1
        elif outcome == 'updated':
            updated += 1
        elif outcome == 'skipped':
            skipped += 1

    if created or updated:
        db.session.commit()
    else:
        db.session.rollback()
    return {'created': created, 'updated': updated, 'skipped': skipped, 'seen': seen}


def _fetch_measure_groups(token: str, since: datetime, until: datetime) -> list:
    """Devuelve los grupos de medida (category=1, medidas reales) en [since, until)."""
    data = {
        'action': 'getmeas',
        'meastypes': _MEASTYPES_PARAM,
        'category': 1,  # 1 = mediciones reales (2 sería objetivos)
        'startdate': int(_to_utc(since).timestamp()),
        'enddate': int(_to_utc(until).timestamp()),
    }
    headers = {'Authorization': f'Bearer {token}'}
    try:
        resp = httpx.post(MEASURE_URL, data=data, headers=headers, timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise WithingsError(f'No se pudo contactar con Withings: {exc}') from exc
    if resp.status_code != 200:
        raise WithingsError(f'Withings devolvió {resp.status_code}: {resp.text[:200]}')
    try:
        wrapper = resp.json()
    except ValueError as exc:
        raise WithingsError('Withings devolvió una respuesta no interpretable.') from exc
    status = wrapper.get('status')
    if status == 401:
        raise WithingsError('Withings rechazó el token (401); reconecta la cuenta.')
    if status != 0:
        raise WithingsError(f'Withings devolvió status {status}: {str(wrapper)[:200]}')
    body = wrapper.get('body') or {}
    return body.get('measuregrps') or []


def _parse_measures(measures: list) -> dict:
    """Convierte la lista de medidas de un grupo a {campo: valor_real}.

    Withings da cada medida como entero con exponente: real = value * 10**unit.
    """
    out: dict = {}
    for measure in measures:
        field = _MEASURE_TYPES.get(measure.get('type'))
        if field is None:
            continue
        value = measure.get('value')
        if value is None:
            continue
        try:
            real = float(value) * (10 ** int(measure.get('unit', 0)))
        except (TypeError, ValueError):
            continue
        out[field] = round(real, 3)
    return out


def debug_measures(since: datetime, until: datetime) -> dict:
    """Diagnóstico (solo lectura): qué grupos devuelve Withings en una ventana.

    Sirve para ver por qué una pesada no cuadra (mapeo de día, escalado de
    unidades). No escribe nada.
    """
    token = valid_access_token()
    if token is None:
        raise WithingsError('Withings no está conectado.')
    tz = _local_tz()
    salida = []
    for group in _fetch_measure_groups(token, since, until):
        ts = group.get('date')
        when = datetime.fromtimestamp(int(ts), tz) if ts is not None else None
        salida.append({
            'grpid': group.get('grpid'),
            'date': when.isoformat() if when else None,
            'mapped_day': when.date().isoformat() if when else None,
            'values': _parse_measures(group.get('measures') or []),
        })
    return {
        'window': {'since': _to_utc(since).isoformat(), 'until': _to_utc(until).isoformat()},
        'timezone': str(tz),
        'count': len(salida),
        'groups': salida,
    }


def _to_utc(when: datetime) -> datetime:
    if when.tzinfo is None:
        return when.replace(tzinfo=timezone.utc)
    return when.astimezone(timezone.utc)


class WithingsError(Exception):
    """Fallo al hablar con Withings (config ausente, token rechazado, red)."""
