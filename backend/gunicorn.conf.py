import os

# El puerto lo inyecta la plataforma (Railway) en $PORT. Se lee aquí, en Python,
# para NO depender de que la shell del CMD expanda variables: si el comando de
# arranque se ejecuta en forma exec (sin shell), un "0.0.0.0:$PORT" llegaría a
# gunicorn con el "$PORT" literal y fallaría ("'$PORT' is not a valid port").
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
workers = 2
timeout = 120
