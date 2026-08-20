"""Herramienta con la que el entrenador responde y registra lo que aprende.

Se usa tool use en vez de pedir JSON en el texto: el historial es conversacional
y el modelo tiende a contestar en prosa ignorando el esquema. Con `tool_choice`
forzado la estructura está garantizada y desaparece el parseo frágil.
(El prefijo de respuesta del asistente no sirve aquí: claude-sonnet-4-6 no lo admite.)
"""

TOOL_NAME = 'responder_y_anotar'

_LIST_OF_TEXT = {'type': 'array', 'items': {'type': 'string'}}

UPDATES_SCHEMA = {
    'type': 'object',
    'description': 'Solo los campos aprendidos o corregidos en ESTE turno.',
    'properties': {
        'age': {'type': 'integer', 'description': 'Edad en años'},
        'sex': {'type': 'string', 'enum': ['male', 'female', 'other']},
        'weight_kg': {'type': 'number', 'description': 'Peso en kilos'},
        'height_cm': {'type': 'number', 'description': 'Altura en centímetros'},
        'training_days_per_week': {'type': 'integer'},
        'activity_level': {
            'type': 'string',
            'enum': ['sedentary', 'light', 'moderate', 'active', 'very_active'],
            'description': 'Dedúcelo combinando trabajo y entrenamiento',
        },
        'job_activity': {'type': 'string', 'enum': ['sedentary', 'standing', 'physical']},
        'job': {'type': 'string', 'description': 'A qué se dedica'},
        'location': {'type': 'string', 'description': 'Dónde vive'},
        'primary_goal': {'type': 'string', 'description': 'Su objetivo principal'},
        'free_notes': {
            'type': 'string',
            'description': 'Contexto o matices que no encajan en ningún campo. Se acumula.',
        },
        # En las listas hay que mandar la lista completa: sustituyen a la anterior.
        'sports': {**_LIST_OF_TEXT, 'description': 'Lista COMPLETA de deportes'},
        'goals': {**_LIST_OF_TEXT, 'description': 'Lista COMPLETA de objetivos'},
        'conditions': {**_LIST_OF_TEXT, 'description': 'Enfermedades o condiciones médicas'},
        'injuries_current': {**_LIST_OF_TEXT, 'description': 'Dolencias o lesiones actuales'},
        'injuries_past': {**_LIST_OF_TEXT, 'description': 'Lesiones pasadas'},
        'diet_notes': {**_LIST_OF_TEXT, 'description': 'Alergias, intolerancias, preferencias'},
        'challenges': {
            'type': 'array',
            'description': 'Retos, competiciones o marcas personales',
            'items': {
                'type': 'object',
                'properties': {
                    'what': {'type': 'string'},
                    'when': {'type': 'string', 'description': 'Fecha o plazo, si lo dice'},
                },
                'required': ['what'],
            },
        },
    },
}

TOOL = {
    'name': TOOL_NAME,
    'description': (
        'Responde al usuario en la conversación y, a la vez, anota lo que has '
        'aprendido de su perfil en este turno. Úsala siempre.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'reply': {
                'type': 'string',
                'description': 'Lo que le dices al usuario. Natural, cercano, una pregunta.',
            },
            'updates': UPDATES_SCHEMA,
            'complete': {
                'type': 'boolean',
                'description': 'true solo si ya tienes lo esencial y no quiere añadir más',
            },
        },
        'required': ['reply'],
    },
}
