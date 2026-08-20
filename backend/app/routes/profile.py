from datetime import date

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..models.user_profile import UserProfile
from ..services import profile_service, targets_service, weight_service
from ..services.claude_service import AnalysisError

profile_bp = Blueprint('profile', __name__)

VALID_SEX = {'male', 'female', 'other'}
VALID_ACTIVITY = {'sedentary', 'light', 'moderate', 'active', 'very_active'}
VALID_JOB_ACTIVITY = {'sedentary', 'standing', 'physical'}
VALID_DIRECTION = set(targets_service.GOAL_DIRECTIONS)
MAX_MESSAGE = 2000


def _payload(profile: UserProfile) -> dict:
    energy = profile_service.estimate_energy(profile)
    return {
        **profile.to_dict(),
        'completeness': profile_service.completeness(profile),
        'missing': profile_service.missing_topics(profile),
        'energy': energy,
        'targets': targets_service.compute(profile, energy),
        'weight': weight_service.summary(profile),
    }


@profile_bp.route('', methods=['GET'])
def get_profile():
    return jsonify(_payload(profile_service.get_or_create()))


@profile_bp.route('', methods=['PATCH'])
def update_profile():
    """Edición manual: el perfil se puede corregir en cualquier momento."""
    profile = profile_service.get_or_create()

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({'error': 'Datos inválidos'}), 400

    if 'sex' in data and data['sex'] not in VALID_SEX and data['sex'] not in (None, ''):
        return jsonify({'error': 'Sexo no válido'}), 400
    if 'activity_level' in data and data['activity_level'] not in VALID_ACTIVITY and data['activity_level'] not in (None, ''):
        return jsonify({'error': 'Nivel de actividad no válido'}), 400
    if 'job_activity' in data and data['job_activity'] not in VALID_JOB_ACTIVITY and data['job_activity'] not in (None, ''):
        return jsonify({'error': 'Tipo de trabajo no válido'}), 400

    if 'goal_direction' in data and data['goal_direction'] not in VALID_DIRECTION and data['goal_direction'] not in (None, ''):
        return jsonify({'error': 'Objetivo no válido'}), 400

    if 'target_overrides' in data:
        raw = data['target_overrides']
        if not isinstance(raw, dict):
            return jsonify({'error': 'Objetivos manuales inválidos'}), 400
        limpio = {}
        for key in ('calories', 'proteins', 'carbs', 'fats', 'fiber'):
            value = raw.get(key)
            if value in (None, ''):
                continue
            try:
                limpio[key] = max(round(float(value)), 0)
            except (TypeError, ValueError):
                return jsonify({'error': 'Los objetivos manuales deben ser numéricos'}), 400
        profile.target_overrides = limpio

    # Vaciar un campo es una edición legítima; apply_updates ignora los vacíos,
    # así que los null se tratan aquí aparte.
    for field, value in data.items():
        if value in (None, '') and field in UserProfile.SCALAR_FIELDS:
            setattr(profile, field, None)
        elif value == [] and field in UserProfile.LIST_FIELDS:
            setattr(profile, field, [])

    profile_service.apply_updates(profile, data)
    db.session.commit()
    return jsonify(_payload(profile))


@profile_bp.route('/chat', methods=['POST'])
def chat():
    """Un turno de la entrevista con el entrenador."""
    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key or api_key.startswith('sk-ant-api03-REEMPLAZA'):
        return jsonify({'error': 'API key de Anthropic no configurada'}), 503

    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()[:MAX_MESSAGE]
    if not message:
        return jsonify({'error': 'Escribe algo para continuar'}), 400

    profile = profile_service.get_or_create()

    try:
        result = profile_service.chat(profile, message)
    except AnalysisError as exc:
        db.session.rollback()
        current_app.logger.error('Respuesta del entrenador no interpretable: %s', exc)
        return jsonify({'error': 'No te he entendido bien. ¿Puedes repetirlo?'}), 502
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error en la conversación del perfil')
        return jsonify({'error': 'Error al hablar con el entrenador. Inténtalo de nuevo.'}), 502

    return jsonify({'reply': result['reply'], 'changed': result['changed'], 'profile': _payload(profile)})


@profile_bp.route('/chat', methods=['DELETE'])
def reset_chat():
    """Reinicia la conversación conservando los datos ya recogidos."""
    profile = profile_service.get_or_create()
    profile_service.reset_conversation(profile)
    return jsonify(_payload(profile))


# ─────────────────────────── peso ───────────────────────────

@profile_bp.route('/weight', methods=['POST'])
def add_weight():
    """Registra una pesada. El peso ya no se sobrescribe: se acumula."""
    profile = profile_service.get_or_create()
    data = request.get_json(silent=True) or {}

    when = None
    if data.get('measured_on'):
        try:
            when = date.fromisoformat(str(data['measured_on']))
        except ValueError:
            return jsonify({'error': 'Fecha inválida, se espera YYYY-MM-DD'}), 400

    try:
        weight_service.record(
            profile,
            data.get('weight_kg'),
            when=when,
            note=str(data.get('note') or '')[:500] or None,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({'error': str(exc)}), 400

    db.session.commit()
    return jsonify(_payload(profile)), 201


@profile_bp.route('/weight/<int:entry_id>', methods=['DELETE'])
def delete_weight(entry_id):
    profile = profile_service.get_or_create()
    if not weight_service.delete(entry_id, profile):
        return jsonify({'error': 'Pesada no encontrada'}), 404
    db.session.commit()
    return jsonify(_payload(profile))
