"""Chat con el entrenador-agente: charla libre con todos los datos como contexto.

Distinto de `/api/profile/chat` (la entrevista que rellena el perfil): aquí el
usuario pregunta lo que quiere y el modelo responde apoyándose en su nutrición,
actividad, gasto, peso y objetivos, consultando el detalle con herramientas.
"""

from flask import Blueprint, current_app, jsonify, request

from .. import db
from ..services import coach_service
from ..services.claude_service import AnalysisError

coach_bp = Blueprint('coach', __name__)

MAX_MESSAGE = coach_service.MAX_MESSAGE


@coach_bp.route('', methods=['GET'])
def get_conversation():
    """Historial de la charla (para pintarla al abrir la pantalla)."""
    return jsonify(coach_service.get_or_create().to_dict())


@coach_bp.route('/chat', methods=['POST'])
def chat():
    """Un turno de charla con el entrenador."""
    api_key = current_app.config.get('ANTHROPIC_API_KEY', '')
    if not api_key or api_key.startswith('sk-ant-api03-REEMPLAZA'):
        return jsonify({'error': 'API key de Anthropic no configurada'}), 503

    data = request.get_json(silent=True) or {}
    message = str(data.get('message', '')).strip()[:MAX_MESSAGE]
    if not message:
        return jsonify({'error': 'Escribe algo para continuar'}), 400

    conv = coach_service.get_or_create()

    try:
        result = coach_service.chat(conv, message)
    except AnalysisError as exc:
        db.session.rollback()
        current_app.logger.error('El entrenador no pudo responder: %s', exc)
        return jsonify({'error': 'No he podido responder ahora mismo. Inténtalo de nuevo.'}), 502
    except Exception:
        db.session.rollback()
        current_app.logger.exception('Error en el chat del entrenador')
        return jsonify({'error': 'Error al hablar con el entrenador. Inténtalo de nuevo.'}), 502

    return jsonify({'reply': result['reply']})


@coach_bp.route('/chat', methods=['DELETE'])
def reset_chat():
    """Reinicia la charla (empieza de cero con el saludo)."""
    conv = coach_service.get_or_create()
    coach_service.reset(conv)
    return jsonify(conv.to_dict())
