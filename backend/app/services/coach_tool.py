"""Herramientas con las que el entrenador-agente consulta los datos a demanda.

El contexto base (perfil, objetivos, últimas semanas, peso) ya viaja en el
prompt de sistema. Estas herramientas son para el detalle fino que no cabe ahí:
qué comió un día concreto, las actividades de un rango, la nutrición día a día
de un periodo. El modelo las llama solo cuando la pregunta lo pide, así el
contexto base se mantiene ligero pero el agente puede bajar al dato exacto.

Las herramientas NO fuerzan `tool_choice`: el modelo decide si necesita datos o
si ya puede responder. El bucle de `coach_service.chat` las ejecuta y le
devuelve el resultado hasta que produce la respuesta final en texto.
"""

_DATE = {
    'type': 'string',
    'description': 'Fecha en formato YYYY-MM-DD (zona horaria del usuario).',
}

CONSULTAR_DIA = {
    'name': 'consultar_dia',
    'description': (
        'Devuelve el detalle de UN día: cada comida registrada (nombre, tipo, '
        'calorías y macros), las actividades hechas, el gasto energético y los '
        'objetivos del día. Úsala cuando pregunten por un día concreto ("¿qué '
        'comí el martes?", "¿cuánto entrené ayer?").'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {'fecha': _DATE},
        'required': ['fecha'],
    },
}

CONSULTAR_NUTRICION = {
    'name': 'consultar_nutricion',
    'description': (
        'Devuelve los totales de nutrición día a día (calorías y macros) entre '
        'dos fechas, ambas incluidas. Úsala para ver la evolución o hacer medias '
        'de un periodo concreto que no esté en el resumen de semanas.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {'desde': _DATE, 'hasta': _DATE},
        'required': ['desde', 'hasta'],
    },
}

CONSULTAR_ACTIVIDADES = {
    'name': 'consultar_actividades',
    'description': (
        'Devuelve las sesiones de actividad física entre dos fechas, ambas '
        'incluidas (deporte, familia, duración, calorías, sensación y métricas '
        'de Whoop si las hay). Úsala para analizar entrenamientos o rendimiento '
        'de un periodo.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {'desde': _DATE, 'hasta': _DATE},
        'required': ['desde', 'hasta'],
    },
}

TOOLS = [CONSULTAR_DIA, CONSULTAR_NUTRICION, CONSULTAR_ACTIVIDADES]
