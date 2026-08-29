from datetime import datetime, timezone

from .. import db


class OAuthState(db.Model):
    """`state` anti-CSRF de un flujo OAuth en curso (Withings/Whoop).

    Se guarda en la BD en vez de en la cookie de sesión de Flask a propósito: la
    vuelta del proveedor al callback es una navegación CROSS-SITE y esa cookie
    (aunque sea SameSite=None) no viaja de forma fiable en la PWA instalada de
    iOS, lo que rompía la validación del `state`. Guardándolo en servidor, el
    `state` viaja solo en la URL (?state=) y se valida contra esta tabla, sin
    depender de ninguna cookie.

    Es efímero: cada fila se borra al consumirse y las caducadas se purgan. En
    una app de usuario único la tabla queda casi siempre vacía.
    """

    __tablename__ = 'oauth_states'

    # El propio `state` (token urlsafe, imposible de adivinar) es la clave.
    state = db.Column(db.String(128), primary_key=True)
    provider = db.Column(db.String(20), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
