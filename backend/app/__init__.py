import os
from flask import Flask
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

    upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), app.config['UPLOAD_FOLDER'])
    os.makedirs(upload_dir, exist_ok=True)
    app.config['UPLOAD_FOLDER_ABS'] = upload_dir

    from .models import (  # noqa: F401
        activity, food_log, food_template, user_profile, weight_entry
    )

    from .routes.food import food_bp
    from .routes.library import library_bp
    from .routes.profile import profile_bp
    from .routes.activity import activity_bp
    app.register_blueprint(food_bp, url_prefix='/api/food')
    app.register_blueprint(library_bp, url_prefix='/api/library')
    app.register_blueprint(profile_bp, url_prefix='/api/profile')
    app.register_blueprint(activity_bp, url_prefix='/api/activities')

    # Candado de acceso (antes que las rutas queden expuestas). Opt-in por
    # APP_ACCESS_TOKEN; sin token no hace nada. Ver app/auth.py.
    from .auth import init_auth
    init_auth(app)

    @app.route('/health')
    def health():
        return {'status': 'ok', 'service': 'fitmoi-api'}

    return app
