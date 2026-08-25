"""Sincronización automática con Whoop al final del día.

A las 00:00 de la zona del usuario (`APP_TIMEZONE`) se traen de Whoop, para
los últimos `WHOOP_SYNC_DAYS` días (hoy incluido y los pasados por si alguno
quedó sin dato):

- el gasto energético TOTAL de cada día -> `energy_expenditures`
  (`sync_daily_energy`, que es la razón de ser de este módulo), y
- los workouts de esos días -> `activities` (`sync_recent_workouts`), para que
  el día quede completo sin tener que tocar el botón de sincronizar a mano.

Con gunicorn hay varios workers y cada uno arranca su propio scheduler: los dos
dispararían el job a medianoche. Un `pg_try_advisory_lock` hace que solo uno lo
ejecute de verdad; el resto se retira sin hacer nada (mismo patrón que
`db_setup.prepare_schema`, con otra clave).
"""

import os

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .services import whoop_service
from .services.whoop_service import WhoopError

# Clave del advisory lock del job nocturno. Distinta de la de prepare_schema
# (918273645) para que no compitan entre sí.
_JOB_LOCK_KEY = 918273646
_JOB_ID = 'whoop-nightly-sync'


def init_scheduler(app):
    """Arranca el scheduler si procede. Idempotente por proceso.

    No arranca si `SCHEDULER_ENABLED` es falso, si Whoop no está configurado
    (sin Client ID/Secret no hay nada que traer), ni en el proceso padre del
    reloader de Werkzeug (dev), que duplicaría el job.
    """
    if not app.config.get('SCHEDULER_ENABLED', True):
        return None

    # El reloader de Werkzeug corre el arranque dos veces (padre y trabajador);
    # solo el trabajador tiene WERKZEUG_RUN_MAIN=true.
    if app.config.get('DEBUG') and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return None

    with app.app_context():
        if not whoop_service.is_configured():
            app.logger.info('Scheduler: Whoop no configurado; sync automático desactivado.')
            return None

    tz = app.config.get('APP_TIMEZONE', 'UTC')
    scheduler = BackgroundScheduler(daemon=True, timezone=tz)
    scheduler.add_job(
        func=lambda: _nightly_sync(app),
        trigger=CronTrigger(hour=0, minute=0, timezone=tz),
        id=_JOB_ID,
        max_instances=1,
        coalesce=True,
        # Si el proceso estaba dormido/reiniciando a medianoche, aún vale la pena
        # ejecutarlo un rato después: la ventana cubre igual el día que acabó.
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.logger.info('Scheduler iniciado: sync de Whoop cada día a las 00:00 (%s).', tz)
    return scheduler


def _nightly_sync(app) -> None:
    """Job de medianoche, protegido para que solo lo ejecute un worker."""
    with app.app_context():
        conn = db.engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        try:
            got = conn.exec_driver_sql(
                'SELECT pg_try_advisory_lock(%s)', (_JOB_LOCK_KEY,)
            ).scalar()
            if not got:
                return  # otro worker se está encargando
            try:
                _run_sync(app)
            finally:
                conn.exec_driver_sql('SELECT pg_advisory_unlock(%s)', (_JOB_LOCK_KEY,))
        finally:
            conn.close()


def _run_sync(app) -> None:
    if not whoop_service.is_connected():
        app.logger.info('Sync nocturno: Whoop sin conectar; se omite.')
        return
    try:
        energy = whoop_service.sync_daily_energy()
        workouts = whoop_service.sync_recent_workouts()
    except WhoopError as exc:
        # Fallo transitorio (token, red): se reintentará mañana; no rompe el proceso.
        app.logger.warning('Sync nocturno de Whoop falló: %s', exc)
        db.session.rollback()
        return
    app.logger.info('Sync nocturno de Whoop OK: gasto=%s workouts=%s', energy, workouts)
