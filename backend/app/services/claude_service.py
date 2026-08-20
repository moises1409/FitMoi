import base64
import json
import re

import anthropic
from flask import current_app

# El orden importa: pedir las calorías directamente hace que el modelo invente
# un número redondo y luego lo justifique. Obligarle a estimar el PESO primero
# y derivar los nutrientes de ahí da estimaciones mucho más contenidas.
METHOD = """Procede EXACTAMENTE en este orden, sin saltarte ningún paso:

1. IDENTIFICA cada alimento con cuidado antes de calcular nada. Fíjate en la
   forma, el color y la textura: bajo una salsa, la pasta rellena, la carne
   desmenuzada y el pescado se confunden con facilidad. La pasta rellena
   (tortellini, ravioli) tiene bordes doblados y forma geométrica repetida; la
   carne tiene fibras irregulares. Si dudas entre dos, dilo en confidence.

2. DECIDE si la foto muestra UNA RACIÓN INDIVIDUAL (plato o bol ya servido) o
   un RECIPIENTE COMPARTIDO (fuente, bandeja de horno, sartén, olla, tupper
   grande). Es la distinción que más equivoca el cálculo.

3. Si es un recipiente compartido, ESTIMA CUÁNTAS RACIONES contiene y trabaja a
   partir de aquí sobre UNA SOLA RACIÓN. El usuario registra lo que se come, no
   lo que ha cocinado. Una fuente de horno familiar suele dar 3-4 raciones.

4. Estima el PESO en gramos (o ml para salsas) de cada alimento EN ESA RACIÓN.
   Calibra con referencias visuales: un plato llano mide 26-28 cm, una fuente de
   horno rectangular 30-35 cm de largo, los cubiertos, un vaso, la mano.

5. SOLO DESPUÉS calcula los nutrientes de cada alimento a partir de ese peso y
   de sus valores por 100 g.

6. Suma los totales de la ración y da un rango realista (mínimo y máximo).

Reglas de estimación:
- Sé conservador. Una ración casera normal pesa menos de lo que parece.
- No confundas el tamaño del recipiente con el de la ración: mira la altura real
  de la comida, no solo la superficie que ocupa.
- Las salsas y los aceites son los que más se subestiman en peso y más pesan en
  calorías: estímalos aparte, nunca los incluyas en el alimento principal.
- Es mucho más útil un rango honesto que un número preciso inventado.
"""

SCHEMA = """Responde ÚNICAMENTE con un objeto JSON válido con esta estructura exacta:
{
  "description": "nombre breve del plato en español",
  "is_shared_dish": false,
  "servings_in_photo": 1,
  "portion_summary": "peso estimado de UNA ración y su desglose; si la foto es una fuente, dilo, ej: fuente de ~900 g ≈ 3 raciones; esta ración ~300 g (200 g de pasta + 100 g de salsa)",
  "foods_detected": [
    {
      "name": "nombre del alimento",
      "grams": 220,
      "quantity": "~220 g",
      "calories": 400,
      "proteins": 17,
      "carbs": 58,
      "fats": 11,
      "saturated_fat": 4,
      "fiber": 3,
      "salt": 1.3
    }
  ],
  "total_calories": 630,
  "calories_min": 540,
  "calories_max": 750,
  "proteins": 21,
  "carbs": 64,
  "fats": 32,
  "saturated_fat": 17,
  "fiber": 3.5,
  "salt": 2.5,
  "confidence": "high|medium|low",
  "assessment": {
    "summary": "qué domina nutricionalmente el plato y por qué, en 1-2 frases",
    "positives": ["lo más sano del plato, 1-3 puntos breves"],
    "concerns": ["lo menos sano del plato, 1-3 puntos breves"],
    "tip": "un consejo concreto y accionable para mejorarlo"
  }
}

- TODOS los valores nutricionales (foods_detected y totales) son de UNA RACIÓN,
  nunca del recipiente entero.
- "is_shared_dish": true si la foto es una fuente/sartén/olla para varias personas.
- "servings_in_photo": cuántas raciones ves en la foto (1 si es un plato individual).
- Todos los valores numéricos deben ser números, no strings. Gramos de macros, sal en gramos.
- "confidence": "high" si el plato y las porciones son claros, "medium" si hay dudas de
  cantidad, "low" si la imagen no permite estimar bien.
- Si no puedes identificar comida, devuelve confidence "low", valores en 0 y explica por qué
  en assessment.summary.
"""

# Se construyen con funciones, no con .format(): SCHEMA contiene las llaves del
# JSON de ejemplo y format() intentaría interpretarlas como campos.
def _image_prompt(subject: str) -> str:
    return f'Analiza {subject} y haz una estimación nutricional.\n\n{METHOD}\n{SCHEMA}'


def _text_prompt(description: str) -> str:
    return (
        'Analiza esta descripción de comida y haz una estimación nutricional.\n\n'
        f'Descripción del usuario:\n"""{description}"""\n\n'
        f'{METHOD}\n'
        'Si el usuario indica cantidades, respétalas en vez de estimarlas.\n\n'
        f'{SCHEMA}'
    )

VALID_CONFIDENCE = {'high', 'medium', 'low'}
MACRO_KEYS = ('proteins', 'carbs', 'fats', 'saturated_fat', 'fiber', 'salt')
_JSON_BLOCK = re.compile(r'\{.*\}', re.DOTALL)


class AnalysisError(RuntimeError):
    """La respuesta del modelo no se pudo interpretar como análisis válido."""


def _to_float(value, default: float = 0.0) -> float:
    """Convierte a float tolerando strings tipo '18.5 g' o None."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.search(r'-?\d+(?:[.,]\d+)?', value)
        if match:
            return float(match.group().replace(',', '.'))
    return default


def _extract_json(raw: str) -> dict:
    """Aísla el objeto JSON aunque venga con vallas ``` o prosa alrededor."""
    text = raw.strip()

    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z]*\s*', '', text)
        text = re.sub(r'\s*```$', '', text)

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = _JSON_BLOCK.search(text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise AnalysisError('El modelo no devolvió un JSON interpretable.')


def _clean_list(value, limit: int = 3) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()][:limit]


def _normalize_assessment(data) -> dict:
    if not isinstance(data, dict):
        return {'summary': '', 'positives': [], 'concerns': [], 'tip': ''}
    return {
        'summary': str(data.get('summary', '')).strip()[:600],
        'positives': _clean_list(data.get('positives')),
        'concerns': _clean_list(data.get('concerns')),
        'tip': str(data.get('tip', '')).strip()[:400],
    }


def _normalize(data: dict) -> dict:
    """Garantiza que el resultado cumple el contrato que espera el frontend."""
    if not isinstance(data, dict):
        raise AnalysisError('El modelo no devolvió un objeto JSON.')

    foods = []
    for item in data.get('foods_detected') or []:
        if not isinstance(item, dict):
            continue
        grams = _to_float(item.get('grams'))
        foods.append({
            'name': str(item.get('name', '')).strip() or 'Alimento',
            'grams': round(grams, 1),
            'quantity': str(item.get('quantity', '')).strip() or (f'~{grams:.0f} g' if grams else ''),
            'calories': round(_to_float(item.get('calories'))),
            **{k: round(_to_float(item.get(k)), 1) for k in MACRO_KEYS},
        })

    confidence = str(data.get('confidence', 'medium')).strip().lower()
    if confidence not in VALID_CONFIDENCE:
        confidence = 'medium'

    total = _to_float(data.get('total_calories'))
    if total <= 0 and foods:
        total = sum(f['calories'] for f in foods)

    lo = _to_float(data.get('calories_min'))
    hi = _to_float(data.get('calories_max'))
    # Sin rango util, uno de +/-15% comunica la incertidumbre real mejor que nada.
    if lo <= 0 or hi <= 0 or lo > hi:
        lo, hi = round(total * 0.85), round(total * 1.15)

    servings = _to_float(data.get('servings_in_photo'), 1.0)
    servings = round(servings) if servings >= 1 else 1

    return {
        'description': str(data.get('description', '')).strip() or 'Plato sin identificar',
        'is_shared_dish': bool(data.get('is_shared_dish')) or servings > 1,
        'servings_in_photo': servings,
        'portion_summary': str(data.get('portion_summary', '')).strip()[:400],
        'foods_detected': foods,
        'total_calories': round(total, 1),
        'calories_min': round(lo, 1),
        'calories_max': round(hi, 1),
        **{k: round(_to_float(data.get(k)), 1) for k in MACRO_KEYS},
        'confidence': confidence,
        'assessment': _normalize_assessment(data.get('assessment')),
    }


def _run(content: list, subject: str) -> dict:
    """Llama al modelo y devuelve el análisis ya validado."""
    client = anthropic.Anthropic(api_key=current_app.config['ANTHROPIC_API_KEY'])

    message = client.messages.create(
        model=current_app.config['ANTHROPIC_MODEL'],
        max_tokens=2048,
        messages=[{'role': 'user', 'content': content}],
    )

    if message.stop_reason == 'refusal':
        raise AnalysisError(f'El modelo rechazó analizar {subject}.')

    text = next((block.text for block in message.content if block.type == 'text'), None)
    if not text:
        raise AnalysisError('El modelo no devolvió texto.')

    if message.stop_reason == 'max_tokens':
        current_app.logger.warning('Analisis truncado por max_tokens')

    return _normalize(_extract_json(text))


def analyze_food_images(images: list[tuple[bytes, str]], user_context: str = '') -> dict:
    """Analiza una o varias fotos del mismo plato, con notas opcionales.

    Varias vistas (desde arriba, de lado, el envase) reducen mucho el error de
    estimación de peso, que es la mayor fuente de error en calorías.
    """
    if not images:
        raise AnalysisError('No se recibió ninguna imagen.')

    content: list = []
    multiple = len(images) > 1

    for index, (image_bytes, media_type) in enumerate(images, start=1):
        if multiple:
            content.append({'type': 'text', 'text': f'Imagen {index}:'})
        content.append({
            'type': 'image',
            'source': {
                'type': 'base64',
                'media_type': media_type,
                'data': base64.standard_b64encode(image_bytes).decode('utf-8'),
            },
        })

    subject = (
        f'estas {len(images)} imágenes del mismo plato' if multiple else 'esta imagen de comida'
    )
    prompt = _image_prompt(subject)
    if user_context:
        prompt += f'\n\nInformación adicional del usuario (tiene prioridad sobre lo que estimes):\n{user_context}'

    content.append({'type': 'text', 'text': prompt})
    return _run(content, 'estas imágenes' if multiple else 'esta imagen')


def analyze_food_text(description: str) -> dict:
    """Analiza una descripción escrita, sin foto."""
    return _run(
        [{'type': 'text', 'text': _text_prompt(description)}],
        'esta descripción',
    )
