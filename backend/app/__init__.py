import os
from flask import Flask, abort, send_file, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_migrate import Migrate
from .config import Config

db = SQLAlchemy()
migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

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
        activity, energy_expenditure, food_log, food_template, user_profile,
        weekly_review, weight_entry
    )

    from .routes.food import food_bp
    from .routes.library import library_bp
    from .routes.profile import profile_bp
    from .routes.activity import activity_bp
    from .routes.energy import energy_bp
    from .routes.review import review_bp
    app.register_blueprint(food_bp, url_prefix='/api/food')
    app.register_blueprint(library_bp, url_prefix='/api/library')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(activity_bp, url_prefix='/api/activities')
    app.register_blueprint(energy_bp, url_prefix='/api/energy')
    app.register_blueprint(review_bp, url_prefix='/api/review')

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
