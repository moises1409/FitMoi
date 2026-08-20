# FitMoi

Aplicación personal de seguimiento nutricional y de actividad física. Registra lo
que comes —por foto, por descripción o reutilizando alimentos ya guardados—, lo
analiza con IA para estimar porciones, calorías y macros, y lo combina con tu
perfil y tu actividad para darte objetivos diarios ajustados a ti.

## Funcionalidades

- **Registro de comidas flexible**: sube una o varias fotos, descríbelo con
  texto, combina ambos, o reutiliza un alimento de tu biblioteca sin volver a
  llamar al modelo.
- **Análisis con IA**: estima la cantidad de cada alimento, calcula calorías y
  nutrientes (proteínas, carbohidratos, grasas, fibra, grasa saturada, sal) y
  señala lo más y lo menos saludable antes de guardar.
- **Biblioteca de alimentos**: cada comida analizada se guarda y se puede
  reutilizar, editar (porciones incluidas) y consultar con su análisis.
- **Calendario**: vista por día, semana y mes con las calorías y los alimentos
  de cada jornada.
- **Perfil como entrenador personal**: un chatbot guía el alta de edad, sexo,
  peso, altura, hábitos deportivos, lesiones, trabajo y objetivos. Editable en
  cualquier momento.
- **Objetivos diarios**: kcal y macros calculados desde el perfil (Mifflin-St
  Jeor + factor de actividad + ajuste por objetivo), visibles en cada día.
- **Historial de peso**: una entrada por medición (cadencia mensual por defecto)
  para seguir la variación en lugar de sobrescribir un único valor.
- **Actividad física**: registro manual con tipo, duración, calorías (opcional),
  sensación y comentarios; el calendario colorea los días según el tipo de
  actividad. Preparado para conectar con Whoop más adelante.

## Stack

- **Backend**: Flask 3 + SQLAlchemy + Flask-Migrate, PostgreSQL 16 (Docker).
  Análisis de imágenes y texto con la API de Anthropic (Claude).
- **Frontend**: Angular 17 (componentes standalone, signals, control flow
  `@if`/`@for`).
- **Imágenes**: Pillow + pillow-heif (HEIC→JPEG, orientación EXIF).

## Puesta en marcha

Requisitos: Python 3.11+, Node 18+, Docker.

```bash
# 1. Base de datos
docker-compose up -d

# 2. Backend
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows;  source .venv/bin/activate en Linux/Mac
pip install -r requirements.txt
cp ../.env.example ../.env     # y rellena ANTHROPIC_API_KEY
python run.py                  # http://localhost:5000

# 3. Frontend
cd frontend
npm install
npm start                      # http://localhost:4200
```

Las migraciones SQL están en [`backend/migrations/`](backend/migrations/) y se
aplican en orden.

## Configuración

Copia `.env.example` a `.env` y ajusta los valores. La clave imprescindible es
`ANTHROPIC_API_KEY` (se obtiene en https://console.anthropic.com). El resto trae
valores por defecto razonables para desarrollo local.
