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


# Fotos que el entrenador puede mirar en una sola consulta, y tamaño al que se
# reducen para ello: con 1024 px se aprecia de sobra la silueta y cada imagen
# cuesta ~1/2 de tokens que a 1568 (el tamaño de guardado).
COACH_MAX_PHOTOS = 8
COACH_PHOTO_DIMENSION = 1024


def photo_index() -> list[dict] | None:
    """Índice compacto de las fotos de progreso por fecha (sin las imágenes)
    para el contexto base del entrenador: así sabe que existen y qué días hay,
    y las pide con su herramienta cuando la pregunta lo requiere. None si no hay
    ninguna."""
    fotos = list(reversed(photo_history()))  # antigua → reciente
    if not fotos:
        return None
    por_dia: dict = {}
    for p in fotos:
        dia = por_dia.setdefault(p.taken_on.isoformat(),
                                 {'fecha': p.taken_on.isoformat(), 'fotos': 0,
                                  'poses': [], 'notas': []})
        dia['fotos'] += 1
        if p.pose and p.pose not in dia['poses']:
            dia['poses'].append(p.pose)
        if p.note and p.note not in dia['notas']:
            dia['notas'].append(p.note)
    salida = []
    for dia in por_dia.values():
        salida.append({k: v for k, v in dia.items() if v})
    return salida


def photos_for_coach(dates: list[date] | None = None,
                     pose: str | None = None) -> list[tuple[BodyPhoto, bytes]]:
    """Fotos (registro + JPEG reducido) para que el entrenador las vea.

    Sin fechas, devuelve la primera y la última fecha con fotos (la comparación
    de evolución que casi siempre interesa). Como mucho COACH_MAX_PHOTOS; si un
    fichero ya no está en disco se omite sin romper.
    """
    query = BodyPhoto.query
    if pose in VALID_POSES:
        query = query.filter(BodyPhoto.pose == pose)

    if not dates:
        fechas = [r[0] for r in query.with_entities(BodyPhoto.taken_on)
                  .distinct().order_by(BodyPhoto.taken_on.asc()).all()]
        dates = sorted({fechas[0], fechas[-1]}) if fechas else []
    if not dates:
        return []

    fotos = (
        query.filter(BodyPhoto.taken_on.in_(dates))
        .order_by(BodyPhoto.taken_on.asc(), BodyPhoto.id.asc())
        .all()
    )

    # Reparto equitativo entre fechas para que una con muchas fotos no deje a
    # las demás fuera del tope.
    por_fecha: dict = {}
    for p in fotos:
        por_fecha.setdefault(p.taken_on, []).append(p)
    elegidas: list[BodyPhoto] = []
    ronda = 0
    while len(elegidas) < COACH_MAX_PHOTOS:
        hubo = False
        for lista in por_fecha.values():
            if ronda < len(lista) and len(elegidas) < COACH_MAX_PHOTOS:
                elegidas.append(lista[ronda])
                hubo = True
        if not hubo:
            break
        ronda += 1
    elegidas.sort(key=lambda p: (p.taken_on, p.id))

    salida = []
    carpeta = photos_dir()
    for p in elegidas:
        try:
            with open(os.path.join(carpeta, p.filename), 'rb') as fh:
                raw = fh.read()
            jpeg, _ = image_service.normalize_image(
                raw, COACH_PHOTO_DIMENSION, current_app.config['IMAGE_JPEG_QUALITY'])
        except (OSError, image_service.UnsupportedImageError):
            current_app.logger.warning('Foto de progreso ilegible: %s', p.filename)
            continue
        salida.append((p, jpeg))
    return salida


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
