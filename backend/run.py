from app import create_app
from app.db_setup import prepare_schema, wait_for_db
from app.scheduler import init_scheduler

app = create_app()

if __name__ == '__main__':
    print('Esperando conexion a PostgreSQL...')
    if not wait_for_db(app):
        print('ERROR: No se pudo conectar a PostgreSQL. Verifica que el contenedor este corriendo.')
        raise SystemExit(1)

    prepare_schema(app)
    print('Base de datos lista.')

    # Sync automatico de Whoop a medianoche (si esta configurado y habilitado).
    init_scheduler(app)

    debug = app.config['DEBUG']
    if debug:
        # El depurador de Werkzeug permite ejecutar codigo arbitrario desde el
        # navegador: con host 0.0.0.0 queda expuesto a toda la red local.
        print('AVISO: modo debug activo y servidor expuesto en la red local.')
        print('       Usa FLASK_DEBUG=0 en .env salvo que estes depurando.')

    print('Servidor Flask en http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000, debug=debug, use_reloader=debug)
