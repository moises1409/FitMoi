"""Entrypoint de producción (gunicorn: `gunicorn wsgi:app`).

A diferencia de `run.py`, aquí la preparación del esquema corre al importar el
módulo —antes de servir— porque bajo gunicorn el bloque `if __name__ ==
'__main__'` de run.py nunca se ejecuta. El advisory lock de `prepare_schema`
hace que sea seguro aunque gunicorn arranque varios workers.
"""

from app import create_app
from app.db_setup import prepare_schema, wait_for_db
from app.scheduler import init_scheduler

app = create_app()

if not wait_for_db(app):
    raise RuntimeError('No se pudo conectar a PostgreSQL al arrancar.')

prepare_schema(app)

# Sync automatico de Whoop a medianoche. Cada worker arranca el suyo; un
# advisory lock evita que se pisen (ver app/scheduler.py).
init_scheduler(app)
