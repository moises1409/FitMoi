import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {'1', 'true', 'yes', 'on'}


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'fitmoi-dev-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'postgresql://fitmoi:fitmoi@localhost:5433/fitmoi')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', 'uploads')
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))

    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
    ANTHROPIC_MODEL = os.environ.get('ANTHROPIC_MODEL', 'claude-sonnet-4-6')
    # Modelo para las tareas de razonamiento largo (el chat del coach y el
    # resumen semanal): merece el modelo mas capaz aunque el analisis de comida
    # siga en el modelo por defecto (mas barato y con vision suficiente).
    ANTHROPIC_COACH_MODEL = os.environ.get('ANTHROPIC_COACH_MODEL', 'claude-opus-4-8')

    # Candado de acceso. Vacio = desactivado (desarrollo local). Al definirlo
    # (produccion/Railway) toda la API exige la cookie de sesion. Ver app/auth.py.
    APP_ACCESS_TOKEN = os.environ.get('APP_ACCESS_TOKEN', '')
    # La cookie solo viaja por HTTPS cuando esto es true: ponlo a 1 en produccion.
    COOKIE_SECURE = _env_bool('COOKIE_SECURE', False)

    # Confiar en las cabeceras X-Forwarded-* del proxy (Railway) para reconstruir
    # el esquema/host reales: sin esto, url_for(_external=True) genera http:// y
    # el redirect_uri de OAuth no cuadra con el https:// registrado. Activo por
    # defecto; ponlo a 0 solo si el servicio queda expuesto SIN un proxy delante.
    TRUST_PROXY = _env_bool('TRUST_PROXY', True)

    # Zona horaria del usuario: determina que cuenta como "hoy" en la vista diaria.
    APP_TIMEZONE = os.environ.get('APP_TIMEZONE', 'Europe/Madrid')

    # Sincronizacion automatica con Whoop a las 00:00 (ver app/scheduler.py).
    # SCHEDULER_ENABLED=0 la desactiva (util en dev). WHOOP_SYNC_DAYS es la
    # ventana que repasa cada noche: hoy y los dias pasados por si alguno quedo
    # sin gasto registrado.
    SCHEDULER_ENABLED = _env_bool('SCHEDULER_ENABLED', True)
    WHOOP_SYNC_DAYS = int(os.environ.get('WHOOP_SYNC_DAYS', 7))

    # Whoop OAuth (esbozo). Vacio = integracion desactivada; /api/whoop/status lo
    # refleja. Al rellenarlos (portal de developer de Whoop) se habilita el flujo.
    # WHOOP_REDIRECT_URI debe COINCIDIR literal con la registrada en el portal;
    # dejala vacia para derivarla de la peticion (vale en local y en produccion).
    WHOOP_CLIENT_ID = os.environ.get('WHOOP_CLIENT_ID', '')
    WHOOP_CLIENT_SECRET = os.environ.get('WHOOP_CLIENT_SECRET', '')
    WHOOP_REDIRECT_URI = os.environ.get('WHOOP_REDIRECT_URI', '')
    WHOOP_SCOPES = os.environ.get('WHOOP_SCOPES', '')

    # Withings OAuth (bascula inteligente). Vacio = integracion desactivada;
    # /api/withings/status lo refleja. Al rellenarlos (portal de developer de
    # Withings) se habilita el flujo. WITHINGS_REDIRECT_URI debe COINCIDIR literal
    # con la registrada en el portal; dejala vacia para derivarla de la peticion.
    # De Withings se traen las mediciones de la bascula (peso + composicion
    # corporal) al historico de peso. WITHINGS_SYNC_DAYS es la ventana que repasa
    # el sync automatico cada noche (por si una pesada llego con retraso).
    WITHINGS_CLIENT_ID = os.environ.get('WITHINGS_CLIENT_ID', '')
    WITHINGS_CLIENT_SECRET = os.environ.get('WITHINGS_CLIENT_SECRET', '')
    WITHINGS_REDIRECT_URI = os.environ.get('WITHINGS_REDIRECT_URI', '')
    WITHINGS_SCOPES = os.environ.get('WITHINGS_SCOPES', '')
    WITHINGS_SYNC_DAYS = int(os.environ.get('WITHINGS_SYNC_DAYS', 30))
    # Ventana AMPLIA que se trae solo al conectar por primera vez, para rellenar
    # de golpe el historico de peso y composicion (y ver el progreso desde ya).
    WITHINGS_INITIAL_SYNC_DAYS = int(os.environ.get('WITHINGS_INITIAL_SYNC_DAYS', 365))

    # Carpeta del build de Angular a servir por Flask (mismo origen -> la cookie
    # del candado funciona sin CORS). Vacio en dev: el frontend lo sirve
    # `ng serve` aparte. En produccion apunta al dist copiado en la imagen.
    FRONTEND_DIST = os.environ.get('FRONTEND_DIST', '')

    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'heic', 'heif'}

    # Toda imagen se normaliza a JPEG con este lado largo maximo antes de
    # enviarla a Claude: evita el limite de 5 MB por imagen y reduce el coste
    # en tokens de vision (1568 px es el maximo util para Sonnet 4.x).
    IMAGE_MAX_DIMENSION = int(os.environ.get('IMAGE_MAX_DIMENSION', 1568))
    IMAGE_JPEG_QUALITY = int(os.environ.get('IMAGE_JPEG_QUALITY', 85))

    # Fotos analizadas pero nunca confirmadas se borran pasadas estas horas.
    ORPHAN_MAX_AGE_HOURS = int(os.environ.get('ORPHAN_MAX_AGE_HOURS', 24))

    DEBUG = _env_bool('FLASK_DEBUG', False)
