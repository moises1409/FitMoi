import time
import sqlalchemy
from app import create_app, db

app = create_app()

def wait_for_db(retries=15, delay=2):
    for i in range(retries):
        try:
            with app.app_context():
                db.engine.connect().close()
            return True
        except sqlalchemy.exc.OperationalError:
            print(f'PostgreSQL no disponible aun, reintentando ({i+1}/{retries})...')
            time.sleep(delay)
    return False

if __name__ == '__main__':
    print('Esperando conexion a PostgreSQL...')
    if not wait_for_db():
        print('ERROR: No se pudo conectar a PostgreSQL. Verifica que el contenedor este corriendo.')
        exit(1)

    with app.app_context():
        db.create_all()
        print('Base de datos inicializada correctamente.')

    debug = app.config['DEBUG']
    if debug:
        # El depurador de Werkzeug permite ejecutar codigo arbitrario desde el
        # navegador: con host 0.0.0.0 queda expuesto a toda la red local.
        print('AVISO: modo debug activo y servidor expuesto en la red local.')
        print('       Usa FLASK_DEBUG=0 en .env salvo que estes depurando.')

    print('Servidor Flask en http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=debug, use_reloader=debug)
