"""Herramienta con la que el LLM redacta el resumen semanal.

Se usa tool use con `tool_choice` forzado en vez de pedir JSON dentro del texto,
por el mismo motivo que el entrenador (`profile_tool`): con un prompt largo y
datos estructurados el modelo tiende a responder en prosa e ignorar el esquema.
Con la herramienta forzada la estructura está garantizada y desaparece el parseo
frágil. El modelo redacta SOLO sobre las cifras que se le pasan; no inventa
números.
"""

TOOL_NAME = 'redactar_resumen_semanal'

_LIST_OF_TEXT = {'type': 'array', 'items': {'type': 'string'}}

TOOL = {
    'name': TOOL_NAME,
    'description': (
        'Redacta el resumen de la semana a partir de las cifras y el perfil que '
        'se te dan. Devuelve qué ha ido bien, qué mejorar, la comparativa con la '
        'semana anterior y recomendaciones. Úsala siempre.'
    ),
    'input_schema': {
        'type': 'object',
        'properties': {
            'resumen': {
                'type': 'string',
                'description': '2-3 frases con la foto general de la semana en '
                               'nutrición y actividad, en relación con el objetivo. '
                               'Si hay datos de composición corporal, menciona su '
                               'evolución (avance o no en grasa/músculo).',
            },
            'lo_bueno': {
                **_LIST_OF_TEXT,
                'description': '2-4 puntos concretos de lo que ha ido bien, '
                               'anclados en las cifras (ej: adherencia a proteína, '
                               'sesiones cumplidas).',
            },
            'a_mejorar': {
                **_LIST_OF_TEXT,
                'description': '2-4 puntos concretos a mejorar, con la cifra que lo '
                               'motiva y, si procede, un umbral objetivo.',
            },
            'comparativa': {
                'type': 'object',
                'description': 'Comparación con la semana anterior. Si no hay datos '
                               'de la semana anterior, tendencia = "sin_datos".',
                'properties': {
                    'tendencia': {
                        'type': 'string',
                        'enum': ['mejor', 'igual', 'peor', 'sin_datos'],
                        'description': 'Valoración global respecto al objetivo, no un '
                                       'único número: pesa nutrición y actividad juntas.',
                    },
                    'detalle': {
                        'type': 'string',
                        'description': 'En qué se ha mejorado o empeorado y por qué, '
                                       'citando los deltas concretos entre semanas.',
                    },
                    'factores': {
                        **_LIST_OF_TEXT,
                        'description': 'Factores concretos detrás del cambio (1-3).',
                    },
                },
                'required': ['tendencia', 'detalle'],
            },
            'recomendaciones': {
                **_LIST_OF_TEXT,
                'description': '2-3 acciones concretas y accionables para la próxima '
                               'semana, coherentes con el objetivo, las lesiones y las '
                               'condiciones médicas del perfil.',
            },
        },
        'required': ['resumen', 'lo_bueno', 'a_mejorar', 'comparativa', 'recomendaciones'],
    },
}
