"""Medidas corporales (cinta) y fotos de progreso.

Dos tipos de seguimiento, ambos fechados para poder ver el histórico por
periodos:

- **Medidas** (`body_measurements`): contornos en cm (cintura, abdomen,
  pectoral, bíceps). Una fila por día (se corrige si se repite el día).
- **Fotos** (`body_photos`): imágenes de progreso, varias por día. El fichero se
  guarda en el subdirectorio `body/` de uploads —NO en la raíz— para que la
  limpieza de fotos huérfanas de comida (`routes/food._cleanup_orphan_photos`,
  que solo mira ficheros de primer nivel) no las borre.

El servicio también expone contexto compacto para el entrenador y el resumen
semanal, para que puedan hablar del progreso de estas medidas.
"""

import os
from datetime import date

from flask import current_app

from .. import db
from ..models.body_measurement import BodyMeasurement
from ..models.body_photo import BodyPhoto
from . import image_service

# Rango razonable de un contorno corporal en cm; fuera de esto es un error de
# tecleo, no un dato.
MIN_CM, MAX_CM = 10.0, 300.0


# ─────────────────────────── almacenamiento de fotos ───────────────────────────

def photos_dir() -> str:
    """Subdirectorio de uploads donde viven las fotos de progreso (aislado de las
    de comida para que no las alcance la limpieza de huérfanas)."""
    base = current_app.config['UPLOAD_FOLDER_ABS']
    path = os.path.join(base, 'body')
    os.makedirs(path, exist_ok=True)
    return path


# ─────────────────────────── medidas ───────────────────────────

def measurement_history(limit: int = 60) -> list:
    return (
        BodyMeasurement.query.order_by(BodyMeasurement.measured_on.desc())
        .limit(limit)
        .all()
    )


def latest_measurement() -> BodyMeasurement | None:
    return BodyMeasurement.query.order_by(BodyMeasurement.measured_on.desc()).first()


def record_measurement(values: dict, when: date | None = None,
                       note: str | None = None) -> BodyMeasurement:
    """Registra (o corrige) las medidas de un día. Solo aplica los contornos que
    vengan con valor numérico válido; exige al menos uno."""
    day = when or date.today()
    if day > date.today():
        raise ValueError('No puedes registrar una toma futura.')

    limpio = {}
    for field in BodyMeasurement.FIELDS:
        raw = values.get(field)
        if raw in (None, ''):
            continue
        try:
            v = round(float(raw), 1)
        except (TypeError, ValueError):
            raise ValueError(f'{BodyMeasurement.LABELS[field]} debe ser numérico.')
        if not (MIN_CM <= v <= MAX_CM):
            raise ValueError(
                f'{BodyMeasurement.LABELS[field]} debe estar entre '
                f'{MIN_CM:.0f} y {MAX_CM:.0f} cm.'
            )
        limpio[field] = v

    if not limpio and not (note and note.strip()):
        raise ValueError('Indica al menos una medida.')

    entry = BodyMeasurement.query.filter_by(measured_on=day).first()
    if entry is None:
        entry = BodyMeasurement(measured_on=day)
        db.session.add(entry)
    for field in BodyMeasurement.FIELDS:
        if field in limpio:
            setattr(entry, field, limpio[field])
    if note is not None:
        entry.note = note or None

    db.session.flush()
    return entry


def delete_measurement(entry_id: int) -> bool:
    entry = db.session.get(BodyMeasurement, entry_id)
    if not entry:
        return False
    db.session.delete(entry)
    db.session.flush()
    return True


def measurement_summary() -> dict:
    """Histórico de medidas (cronológico) + valor actual y variación por contorno."""
    entries = measurement_history()
    if not entries:
        return {'entries': [], 'latest': None, 'changes': {}}

    cronologico = list(reversed(entries))  # antigua → reciente
    latest = entries[0]

    changes = {}
    for field in BodyMeasurement.FIELDS:
        serie = [(e.measured_on, getattr(e, field)) for e in cronologico
                 if getattr(e, field) is not None]
        if not serie:
            continue
        actual = serie[-1][1]
        primera = serie[0][1]
        anterior = serie[-2][1] if len(serie) > 1 else None
        changes[field] = {
            'label': BodyMeasurement.LABELS[field],
            'current': actual,
            'change_last': round(actual - anterior, 1) if anterior is not None else None,
            'change_total': round(actual - primera, 1) if len(serie) > 1 else None,
        }

    return {
        'entries': [e.to_dict() for e in cronologico],
        'latest': latest.to_dict(),
        'changes': changes,
    }


# ─────────────────────────── fotos ───────────────────────────

VALID_POSES = {'frente', 'perfil', 'espalda', 'otra'}


def add_photo(raw_bytes: bytes, when: date | None = None,
              pose: str | None = None, note: str | None = None) -> BodyPhoto:
    """Normaliza y guarda una foto de progreso fechada."""
    day = when or date.today()
    if day > date.today():
        raise ValueError('No puedes registrar una foto futura.')

    image_bytes, _ = image_service.normalize_image(
        raw_bytes,
        current_app.config['IMAGE_MAX_DIMENSION'],
        current_app.config['IMAGE_JPEG_QUALITY'],
    )
    filename = image_service.persist_jpeg(image_bytes, photos_dir())

    photo = BodyPhoto(
        taken_on=day,
        pose=pose if pose in VALID_POSES else None,
        filename=filename,
        note=(note or None),
    )
    db.session.add(photo)
    db.session.flush()
    return photo


def photo_history(limit: int = 200) -> list:
    return (
        BodyPhoto.query
        .order_by(BodyPhoto.taken_on.desc(), BodyPhoto.id.desc())
        .limit(limit)
        .all()
    )


def delete_photo(photo_id: int) -> bool:
    photo = db.session.get(BodyPhoto, photo_id)
    if not photo:
        return False
    # Se borra primero el registro; el fichero se intenta borrar sin romper si ya
    # no está (el registro es la fuente de verdad de lo que existe).
    fname = photo.filename
    db.session.delete(photo)
    db.session.flush()
    try:
        os.remove(os.path.join(photos_dir(), fname))
    except OSError:
        pass
    return True


def summary() -> dict:
    """Todo el progreso corporal: medidas (con variaciones) + fotos."""
    return {
        'measurements': measurement_summary(),
        'photos': [p.to_dict() for p in photo_history()],
    }


# ─────────────────────────── contexto para coach / resumen ───────────────────────────

def coach_context() -> dict | None:
    """Medidas corporales compactas para el entrenador: actual + variación y las
    últimas tomas. None si no hay ninguna medida registrada."""
    resumen = measurement_summary()
    if not resumen['entries']:
        return None

    actuales = {}
    for field, info in resumen['changes'].items():
        actuales[BodyMeasurement.LABELS[field]] = {
            'cm': info['current'],
            'cambio_desde_anterior': info['change_last'],
            'cambio_total': info['change_total'],
        }

    tomas = [
        {'fecha': e['measured_on'],
         **{BodyMeasurement.LABELS[f]: e[f] for f in BodyMeasurement.FIELDS if e[f] is not None}}
        for e in resumen['entries'][-6:]
    ]
    return {'medidas_actuales': actuales, 'ultimas_tomas': tomas}


def measurement_metrics_between(start: date, end: date) -> dict:
    """Inicio/fin/variación de cada contorno dentro de [start, end] (para el
    resumen semanal). Solo cuentan las tomas que traen cada medida."""
    filas = (
        BodyMeasurement.query
        .filter(BodyMeasurement.measured_on >= start,
                BodyMeasurement.measured_on <= end)
        .order_by(BodyMeasurement.measured_on.asc())
        .all()
    )
    out: dict = {}
    for field in BodyMeasurement.FIELDS:
        serie = [getattr(f, field) for f in filas if getattr(f, field) is not None]
        if not serie:
            continue
        out[field] = {
            'label': BodyMeasurement.LABELS[field],
            'inicio': serie[0],
            'fin': serie[-1],
            'variacion': round(serie[-1] - serie[0], 1) if len(serie) > 1 else None,
        }
    return out
