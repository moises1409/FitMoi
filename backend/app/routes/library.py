import os

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..models.food_template import FoodTemplate
from ..services import library_service
from ..services.claude_service import AnalysisError, analyze_food_images
from ..services.image_service import UnsupportedImageError, normalize_image, persist_jpeg
from ..services.library_service import MACRO_KEYS

library_bp = Blueprint('library', __name__)

VALID_KINDS = {'dish', 'food'}
VALID_MEAL_TYPES = {'breakfast', 'lunch', 'snack', 'dinner'}


COMPONENT_MACROS = ('proteins', 'carbs', 'fats', 'saturated_fat', 'fiber', 'salt')


def _clean_components(raw: list) -> list:
    """Normaliza el desglose por alimento que llega editado desde la app."""
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name', '')).strip()
        if not name:
            continue
        grams = _macro(item.get('grams'), 'grams')
        entry = {
            'name': name[:200],
            'grams': round(grams, 1),
            'quantity': str(item.get('quantity', '')).strip()[:80] or (f'~{grams:.0f} g' if grams else ''),
            'calories': round(_macro(item.get('calories'), 'calories')),
        }
        for key in COMPONENT_MACROS:
            if key in item:
                entry[key] = round(_macro(item.get(key), key), 1)
        out.append(entry)
    return out[:40]


def _macro(value, field: str) -> float:
    if value is None or value == '':
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f'El campo "{field}" debe ser numérico.')
    if number != number or number in (float('inf'), float('-inf')):
        raise ValueError(f'El campo "{field}" no es un número válido.')
    return max(number, 0.0)


@library_bp.route('/suggest', methods=['GET'])
def suggest():
    """Sugerencias para la pantalla de añadir, sesgadas por franja horaria."""
    meal_type = request.args.get('meal_type')
    if meal_type not in VALID_MEAL_TYPES:
        meal_type = None
    limit = min(max(request.args.get('limit', 8, type=int), 1), 20)
    return jsonify(library_service.suggest(meal_type, limit))


@library_bp.route('', methods=['GET'])
def list_templates():
    query = request.args.get('q', '').strip()
    limit = min(max(request.args.get('limit', 50, type=int), 1), 200)
    results = library_service.search(query, limit)
    return jsonify({'items': [t.to_dict() for t in results], 'query': query})


@library_bp.route('', methods=['POST'])
def create_template():
    """Alta manual: para alimentos habituales cuyos macros ya conoces."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    name = str(data.get('name', '')).strip()
    if not name:
        return jsonify({'error': 'El nombre es obligatorio'}), 400

    if library_service.find_by_name(name):
        return jsonify({'error': f'Ya existe "{name}" en tu biblioteca'}), 409

    kind = str(data.get('kind', 'food')).strip().lower()
    if kind not in VALID_KINDS:
        kind = 'food'

    try:
        macros = {k: _macro(data.get(k), k) for k in MACRO_KEYS}
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    template = library_service.upsert_template(
        name=name,
        macros=macros,
        kind=kind,
        quantity_label=str(data.get('quantity_label', '')),
        components=data.get('components') if isinstance(data.get('components'), list) else [],
        source='manual',
    )
    db.session.commit()
    return jsonify(template.to_dict()), 201


@library_bp.route('/<int:template_id>', methods=['PATCH'])
def update_template(template_id):
    template = db.session.get(FoodTemplate, template_id)
    if not template:
        return jsonify({'error': 'No encontrado'}), 404

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    if 'name' in data:
        name = str(data['name']).strip()
        if not name:
            return jsonify({'error': 'El nombre no puede estar vacío'}), 400
        key = library_service.normalize_name(name)
        clash = FoodTemplate.query.filter_by(normalized_name=key).first()
        if clash and clash.id != template.id:
            return jsonify({'error': f'Ya existe "{name}" en tu biblioteca'}), 409
        template.name = name[:200]
        template.normalized_name = key[:200]

    if 'quantity_label' in data:
        template.quantity_label = str(data['quantity_label'])[:80]

    try:
        for key in MACRO_KEYS:
            if key in data:
                setattr(template, key, _macro(data[key], key))
        if isinstance(data.get('components'), list):
            template.components = _clean_components(data['components'])
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400

    # portion_summary editable: es la frase que explica de dónde salen los pesos.
    if 'portion_summary' in data:
        analysis = dict(template.analysis or {})
        analysis['portion_summary'] = str(data['portion_summary']).strip()[:400]
        template.analysis = analysis

    # Los días donde aparece este alimento se corrigen también.
    updated = library_service.propagate_to_logs(template)
    db.session.commit()

    return jsonify({**template.to_dict(), 'logs_updated': updated})


@library_bp.route('/<int:template_id>', methods=['DELETE'])
def delete_template(template_id):
    template = db.session.get(FoodTemplate, template_id)
    if not template:
        return jsonify({'error': 'No encontrado'}), 404

    # Quitar un alimento del catálogo no borra las comidas que ya te comiste:
    # los registros conservan sus datos y solo dejan de apuntar a la plantilla.
    unlinked = library_service.unlink_from_logs(template_id)

    db.session.delete(template)
    db.session.commit()
    return jsonify({'message': 'Eliminado de la biblioteca', 'logs_unlinked': unlinked})


@library_bp.route('/<int:template_id>/photo', methods=['POST'])
def set_photo(template_id):
    """Cambia la imagen del alimento (y la de los días que no tenían foto)."""
    template = db.session.get(FoodTemplate, template_id)
    if not template:
        return jsonify({'error': 'No encontrado'}), 404

    file = request.files.get('photo')
    if not file or not file.filename:
        return jsonify({'error': 'No se proporcionó ninguna imagen'}), 400

    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'error': 'Tipo de archivo no permitido'}), 400

    try:
        image_bytes, _ = normalize_image(
            file.read(),
            current_app.config['IMAGE_MAX_DIMENSION'],
            current_app.config['IMAGE_JPEG_QUALITY'],
        )
    except UnsupportedImageError as exc:
        return jsonify({'error': str(exc)}), 400

    template.photo_path = persist_jpeg(image_bytes, current_app.config['UPLOAD_FOLDER_ABS'])
    updated = library_service.propagate_to_logs(template)
    db.session.commit()

    return jsonify({**template.to_dict(), 'logs_updated': updated})


@library_bp.route('/<int:template_id>/reanalyze', methods=['POST'])
def reanalyze(template_id):
    """Vuelve a analizar el alimento a partir de su foto guardada.

    Sirve para los alimentos registrados antes de que el análisis estimara el
    peso de las porciones: actualiza macros y valoración, y corrige los días
    donde aparecen.
    """
    template = db.session.get(FoodTemplate, template_id)
    if not template:
        return jsonify({'error': 'No encontrado'}), 404

    if not template.photo_path:
        return jsonify({'error': 'Este alimento no tiene foto guardada para reanalizar'}), 400

    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key or api_key.startswith('sk-ant-api03-REEMPLAZA'):
        return jsonify({'error': 'API key de Anthropic no configurada'}), 503

    path = os.path.join(
        current_app.config['UPLOAD_FOLDER_ABS'], os.path.basename(template.photo_path)
    )
    try:
        with open(path, 'rb') as handle:
            raw = handle.read()
    except OSError:
        return jsonify({'error': 'La foto ya no está disponible en el servidor'}), 404

    try:
        image = normalize_image(
            raw,
            current_app.config['IMAGE_MAX_DIMENSION'],
            current_app.config['IMAGE_JPEG_QUALITY'],
        )
        # El nombre actual se pasa como contexto: el usuario ya lo ha validado.
        result = analyze_food_images([image], f'El plato es: {template.name}')
    except UnsupportedImageError as exc:
        return jsonify({'error': str(exc)}), 400
    except AnalysisError as exc:
        current_app.logger.error('Reanalisis no interpretable: %s', exc)
        return jsonify({'error': 'No se pudo interpretar el análisis. Inténtalo de nuevo.'}), 502
    except Exception:
        current_app.logger.exception('Error reanalizando la plantilla %s', template_id)
        return jsonify({'error': 'Error al reanalizar. Inténtalo de nuevo.'}), 502

    template.calories = result['total_calories']
    for key in ('proteins', 'carbs', 'fats', 'fiber', 'saturated_fat', 'salt'):
        setattr(template, key, result[key])
    template.components = result['foods_detected']
    template.analysis = {
        'is_shared_dish': result['is_shared_dish'],
        'servings_in_photo': result['servings_in_photo'],
        'portion_summary': result['portion_summary'],
        'calories_min': result['calories_min'],
        'calories_max': result['calories_max'],
        'assessment': result['assessment'],
    }

    updated = library_service.propagate_to_logs(template)
    db.session.commit()

    return jsonify({**template.to_dict(), 'logs_updated': updated})


@library_bp.route('/<int:template_id>/photo', methods=['DELETE'])
def clear_photo(template_id):
    template = db.session.get(FoodTemplate, template_id)
    if not template:
        return jsonify({'error': 'No encontrado'}), 404

    template.photo_path = None
    db.session.commit()
    return jsonify(template.to_dict())


@library_bp.route('/<int:template_id>/merge', methods=['POST'])
def merge_template(template_id):
    """Funde un duplicado en otra entrada, sumando su historial de uso."""
    data = request.get_json(silent=True) or {}
    target_id = data.get('into_id')
    if not isinstance(target_id, int):
        return jsonify({'error': 'Falta into_id'}), 400

    target = library_service.merge(template_id, target_id)
    if not target:
        return jsonify({'error': 'No se pudo fusionar'}), 400

    db.session.commit()
    return jsonify(target.to_dict())
