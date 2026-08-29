"""Emisión y validación del `state` de OAuth, respaldado en la BD.

Sustituye a guardar el `state` en la cookie de sesión de Flask: esa cookie no
sobrevive de forma fiable a la vuelta cross-site desde el proveedor (Withings/
Whoop) en la PWA de iOS. Aquí el `state` vive en la tabla `oauth_states` y se
valida contra ella, así que el round-trip no depende de ninguna cookie.
"""

from datetime import datetime, timedelta, timezone

from .. import db
from ..models.oauth_state import OAuthState

# Ventana de validez del state: de sobra para autorizar y volver, sin dejar
# tokens colgando indefinidamente.
_TTL = timedelta(minutes=15)


def issue(provider: str, state: str) -> None:
    """Guarda un `state` recién generado para `provider`. Purga los caducados."""
    _prune()
    db.session.add(OAuthState(state=state, provider=provider))
    db.session.commit()


def consume(provider: str, state: str) -> bool:
    """Valida y CONSUME un `state`: True solo si existe, es de este proveedor y
    no ha caducado. En cualquier caso lo borra si lo encuentra (un state es de
    un solo uso)."""
    if not state:
        return False
    row = db.session.get(OAuthState, state)
    if row is None:
        return False
    valido = row.provider == provider and _is_fresh(row)
    db.session.delete(row)
    db.session.commit()
    return valido


def _is_fresh(row: OAuthState) -> bool:
    created = row.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - created <= _TTL


def _prune() -> None:
    cutoff = datetime.now(timezone.utc) - _TTL
    db.session.query(OAuthState).filter(OAuthState.created_at < cutoff).delete()
