"""Medidas corporales y fotos de progreso.

  GET    /api/body                    -> resumen (medidas con variaciones + fotos)
  POST   /api/body/measurements       -> registra/corrige las medidas de un día
  DELETE /api/body/measurements/<id>  -> borra una toma
  POST   /api/body/photos             -> sube una foto de progreso (multipart)
  DELETE /api/body/photos/<id>        -> borra una foto (registro + fichero)
  GET    /api/body/photos/<filename>  -> sirve la imagen (bajo el candado, cookie)

Todo vive bajo /api/ y por tanto lo cubre el candado (app/auth.py). Las fotos se
sirven por cookie, así que un <img src="/api/body/photos/..."> funciona en el SPA.
"""

from datetime import date

from flask import Blueprint, current_app, jsonify, request, send_from_directory

from .. import db
from ..services import body_service
from ..services.image_service import UnsupportedImageError

body_bp = Blueprint('body', __name__)

MAX_NOTE = 500


def _payload() -> dict:
    return body_service.summary()


@body_bp.route('', methods=['GET'])
def get_body():
    return jsonify(_payload())


# ─────────────────────────── medidas ───────────────────────────

@body_bp.route('/measurements', methods=['POST'])
def add_measurement():
    data = request.get_json(silent=True) or {}

    when = None
    if data.get('measured_on'):
        try:
            when = date.fromisoformat(str(data['measured_on']))
        except ValueError:
            return jsonify({'error': 'Fecha inválida, se espera YYYY-MM-DD'}), 400

    note = data.get('note')
    if note is not None:
        note = str(note)[:MAX_NOTE]

    try:
        body_service.record_measurement(data, when=when, note=note)
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    return jsonify(_payload()), 201


@body_bp.route('/measurements/<int:entry_id>', methods=['DELETE'])
def delete_measurement(entry_id):
    if not body_service.delete_measurement(entry_id):
        return jsonify({'error': 'Toma no encontrada'}), 404
    db.session.commit()
    return jsonify(_payload())


# ─────────────────────────── fotos ───────────────────────────

@body_bp.route('/photos', methods=['POST'])
def add_photo():
    # Se pueden subir varias fotos de una vez (campo 'photos'); se acepta 'photo'
    # en singular por compatibilidad.
    files = [f for f in request.files.getlist('photos') if f and f.filename]
    single = request.files.get('photo')
    if not files and single and single.filename:
        files = [single]
    if not files:
        return jsonify({'error': 'Falta la foto.'}), 400

    when = None
    if request.form.get('taken_on'):
        try:
            when = date.fromisoformat(str(request.form['taken_on']))
        except ValueError:
            return jsonify({'error': 'Fecha inválida, se espera YYYY-MM-DD'}), 400

    note = (request.form.get('note') or '')[:MAX_NOTE] or None

    try:
        for f in files:
            body_service.add_photo(f.read(), when=when, note=note)
    except UnsupportedImageError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    return jsonify(_payload()), 201


@body_bp.route('/photos/<int:photo_id>', methods=['DELETE'])
def delete_photo(photo_id):
    if not body_service.delete_photo(photo_id):
        return jsonify({'error': 'Foto no encontrada'}), 404
    db.session.commit()
    return jsonify(_payload())


@body_bp.route('/photos/<filename>', methods=['GET'])
def serve_photo(filename):
    # send_from_directory bloquea el path traversal (safe_join).
    return send_from_directory(
        body_service.photos_dir(), filename, max_age=60 * 60 * 24 * 30
    )
