import os
from flask import Flask, abort, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # La cookie de sesión de Flask solo transporta el `state` de OAuth
    # (Withings/Whoop). Ese `state` debe sobrevivir a la vuelta CROSS-SITE desde
    # el proveedor al callback; con SameSite=Lax el navegador la descarta en ese
    # salto (sobre todo en la PWA de iOS) y la validación del state fallaría. En
    # producción (HTTPS) se marca SameSite=None + Secure para que sí viaje; en
    # dev (HTTP) eso no es válido, así que se deja en Lax (el OAuth local va por
    # localhost, mismo sitio, y no hay problema).
    if app.config.get('COOKIE_SECURE'):
        app.config['SESSION_COOKIE_SAMESITE'] = 'None'
        app.config['SESSION_COOKIE_SECURE'] = True
    else:
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # En producción (Railway) el proxy termina el TLS y le pasa la petición a
    # Flask como http; sin esto, `url_for(_external=True)` genera URLs http:// y
    # el redirect_uri de OAuth (Withings/Whoop) no cuadra con el https:// que se
    # registró en cada portal (redirect_uri_mismatch). ProxyFix hace que Flask
    # confíe en X-Forwarded-Proto/Host del proxy y reconstruya el esquema y host
    # reales. Se aplica solo si hay un proxy delante (TRUST_PROXY, activo por
    # defecto): en dev, sin proxy, esas cabeceras no existen y no cambia nada.
    if app.config.get('TRUST_PROXY', True):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    db.init_app(app)
    migrate.init_app(app, db)

    # UPLOAD_FOLDER absoluto (p. ej. un volumen de Railway montado en /data/uploads)
    # se usa tal cual; relativo se ancla a la carpeta backend/. En Railway el disco
    # del contenedor es efímero: sin un volumen apuntado aquí, las fotos se borran
    # en cada deploy.
    upload_folder = app.config['UPLOAD_FOLDER']
    if os.path.isabs(upload_folder):
        upload_dir = upload_folder
    else:
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), upload_folder)
    os.makedirs(upload_dir, exist_ok=True)
    app.config['UPLOAD_FOLDER_ABS'] = upload_dir

    from .models import (  # noqa: F401
        activity, body_measurement, body_photo, coach_conversation,
        energy_expenditure, food_log, food_template, oauth_state, user_profile,
        weekly_review, weight_entry, whoop_token, withings_token,
    )

    from .routes.food import food_bp
    from .routes.library import library_bp
    from .routes.profile import profile_bp
    from .routes.activity import activity_bp
    from .routes.energy import energy_bp
    from .routes.review import review_bp
    from .routes.whoop import whoop_bp
    from .routes.withings import withings_bp
    from .routes.body import body_bp
    from .routes.coach import coach_bp
    app.register_blueprint(food_bp, url_prefix='/api/food')
    app.register_blueprint(library_bp, url_prefix='/api/library')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(activity_bp, url_prefix='/api/activities')
    app.register_blueprint(energy_bp, url_prefix='/api/energy')
    app.register_blueprint(review_bp, url_prefix='/api/review')
    app.register_blueprint(whoop_bp, url_prefix='/api/whoop')
    app.register_blueprint(withings_bp, url_prefix='/api/withings')
    app.register_blueprint(body_bp, url_prefix='/api/body')
    app.register_blueprint(coach_bp, url_prefix='/api/coach')

    # Candado de acceso (antes que las rutas queden expuestas). Opt-in por
    # APP_ACCESS_TOKEN; sin token no hace nada. Ver app/auth.py.
    from .auth import init_auth
    init_auth(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'fitmoi-api'}

    # Política de privacidad: página pública y estática. Debe ser accesible SIN
    # candado (el revisor de Whoop la abre sin login) y sin caer en el SPA de
    # Angular, cuyo authGuard redirigiría a /login. El candado ya deja pasar todo
    # lo que no empieza por /api/ (ver app/auth.py), y esta regla estática tiene
    # prioridad sobre el catch-all <path:path> del frontend.
    @app.route('/privacy')
    def privacy():
        return send_file(os.path.join(os.path.dirname(__file__), 'static_pages', 'privacy.html'))

    _register_frontend(app)

    return app


def _register_frontend(app):
    """Sirve el build de Angular desde el propio Flask (mismo origen).

    En dev FRONTEND_DIST está vacío y el frontend lo sirve `ng serve` en :4200,
    así que esto no se registra. En producción sirve los ficheros del SPA y, para
    cualquier ruta que no sea un archivo ni la API, devuelve index.html para que
    el enrutado de Angular funcione al recargar o entrar directo a /calendar, etc.
    """
    dist = app.config.get('FRONTEND_DIST', '')
    if not dist or not os.path.isdir(dist):
        return

    index_file = os.path.join(dist, 'index.html')

    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def spa(path):
        # La API y /health tienen sus propias rutas; aquí no se tocan.
        if path.startswith('api/') or path == 'health':
            abort(404)
        target = os.path.join(dist, path)
        if path and os.path.isfile(target):
            return send_from_directory(dist, path)
        return send_file(index_file)
