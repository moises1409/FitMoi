"""Preparación del esquema al arrancar.

En una BD nueva (p. ej. Railway) `db.create_all()` construye el esquema COMPLETO:
los modelos ya reflejan todas las columnas, tipos (`timestamptz`), índices y
uniques que en su día añadieron los `.sql` de `migrations/`. Por eso esos `.sql`
son deltas HISTÓRICOS que no deben re-ejecutarse sobre una BD que ya está al día
— la 001 (cambio de tipo con `USING ... AT TIME ZONE`) hasta desplazaría las
fechas si corriera sobre datos reales.

Estrategia:
- `create_all()` crea lo que falte (todo en una BD fresca; nada en una existente).
- `schema_migrations` registra qué `.sql` se han aplicado.
- La PRIMERA vez (aún sin tabla de registro) se toman los `.sql` presentes como
  BASELINE ya satisfecho por `create_all` y se marcan aplicados SIN ejecutarlos.
  Así una BD nueva queda correcta y una BD existente NO re-ejecuta la 001.
- Los `.sql` que se añadan después (008+) sí se ejecutan una vez y se registran.

Con gunicorn arrancan varios workers a la vez: un advisory lock de Postgres
serializa la preparación para que no compitan al crear tablas o migrar.
"""

import os
import time

import sqlalchemy
from sqlalchemy import text

from . import db

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'migrations')
# Clave arbitraria y fija para el advisory lock de preparación del esquema.
_LOCK_KEY = 918273645


def wait_for_db(app, retries: int = 30, delay: int = 2) -> bool:
    """Espera a que PostgreSQL acepte conexiones (el servicio puede tardar)."""
    with app.app_context():
        for attempt in range(1, retries + 1):
            try:
                db.engine.connect().close()
                return True
            except sqlalchemy.exc.OperationalError:
                app.logger.warning('PostgreSQL no disponible, reintento %d/%d', attempt, retries)
                time.sleep(delay)
    return False


def _migration_files() -> list[str]:
    if not os.path.isdir(MIGRATIONS_DIR):
        return []
    return sorted(f for f in os.listdir(MIGRATIONS_DIR) if f.endswith('.sql'))


def prepare_schema(app) -> None:
    with app.app_context():
        with db.engine.connect() as conn:
            conn = conn.execution_options(isolation_level='AUTOCOMMIT')
            conn.exec_driver_sql('SELECT pg_advisory_lock(%s)', (_LOCK_KEY,))
            try:
                # En una BD nueva, crea el esquema completo desde los modelos.
                db.create_all()

                conn.exec_driver_sql(
                    'CREATE TABLE IF NOT EXISTS schema_migrations ('
                    ' filename TEXT PRIMARY KEY,'
                    ' applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())'
                )
                applied = {
                    row[0]
                    for row in conn.exec_driver_sql('SELECT filename FROM schema_migrations')
                }
                files = _migration_files()

                if not applied:
                    # Baseline: create_all ya dejó el esquema al día; los deltas
                    # históricos se registran como aplicados sin ejecutarlos.
                    for name in files:
                        conn.exec_driver_sql(
                            'INSERT INTO schema_migrations (filename) VALUES (%s)'
                            ' ON CONFLICT DO NOTHING',
                            (name,),
                        )
                    app.logger.info('schema_migrations: baseline de %d migración(es)', len(files))
                    return

                # Arranques posteriores: solo lo nuevo, una vez cada uno.
                for name in files:
                    if name in applied:
                        continue
                    sql = open(os.path.join(MIGRATIONS_DIR, name), encoding='utf-8').read()
                    conn.exec_driver_sql(sql)  # cada .sql trae su propio BEGIN/COMMIT
                    conn.exec_driver_sql(
                        'INSERT INTO schema_migrations (filename) VALUES (%s)'
                        ' ON CONFLICT DO NOTHING',
                        (name,),
                    )
                    app.logger.info('migración aplicada: %s', name)
            finally:
                conn.exec_driver_sql('SELECT pg_advisory_unlock(%s)', (_LOCK_KEY,))
