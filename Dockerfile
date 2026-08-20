# Imagen única que sirve backend Flask + frontend Angular desde el mismo origen
# (así la cookie del candado funciona sin CORS y Railway despliega una sola pieza).

# --- Etapa 1: build del frontend Angular ---
FROM node:20-alpine AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npx ng build --configuration production

# --- Etapa 2: backend Flask, que sirve también el SPA construido ---
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/ ./backend/
# El SPA compilado, a una carpeta que Flask sirve (FRONTEND_DIST lo apunta).
COPY --from=frontend /build/dist/frontend/browser ./frontend_dist
ENV FRONTEND_DIST=/app/frontend_dist \
    UPLOAD_FOLDER=/data/uploads

# Railway inyecta $PORT; 8080 como valor por defecto para correr en local.
EXPOSE 8080
CMD ["sh", "-c", "gunicorn --chdir backend --bind 0.0.0.0:${PORT:-8080} --workers 2 --timeout 120 wsgi:app"]
