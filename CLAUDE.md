# CLAUDE.md

Contexto del proyecto para Claude Code. Léelo antes de tocar nada: recoge cómo
arrancar, la arquitectura y —sobre todo— trampas que ya costaron caras y no
conviene volver a descubrir.

## Qué es

**FitMoi**: app personal de seguimiento nutricional y de actividad física. Se
registra la comida (por foto, por descripción o reutilizando la biblioteca), se
analiza con IA (Claude, visión + texto) para estimar porciones, calorías y
macros, y se combina con el perfil del usuario y su actividad para dar objetivos
diarios ajustados. MVP de **usuario único, sin autenticación**.

## Stack

- **Backend**: Python/Flask en `backend/` con SQLAlchemy + Flask-Migrate.
- **BD**: PostgreSQL vía Docker Compose — **host 5433** → contenedor 5432.
- **Frontend**: Angular 17 (Node 20; no compatible con Angular 18+) en `frontend/`.
- **LLM**: Claude visión + texto. Modelo en `ANTHROPIC_MODEL` (por defecto
  `claude-sonnet-4-6`). Requiere `ANTHROPIC_API_KEY`.

## Arrancar (desarrollo)

Requisitos: Python 3.11+, Node 20, Docker.

```bash
docker-compose up -d                      # Postgres en :5433
cp .env.example .env                       # y rellenar ANTHROPIC_API_KEY

cd backend
python -m venv .venv && . .venv/Scripts/activate   # o source .venv/bin/activate
pip install -r requirements.txt
python run.py                              # Flask en :5000

cd ../frontend
npm install
npm start                                  # Angular en :4200
```

En Windows hay scripts: `.\start-backend.ps1` y `.\start-frontend.ps1`.

`.env` **no está en el repo** (lleva la clave real). Copia `.env.example` y
rellénalo; sin `ANTHROPIC_API_KEY` el análisis de comida no funciona.

## Migraciones y arranque del esquema

`backend/app/db_setup.py::prepare_schema()` se ejecuta al arrancar (lo llaman
`run.py` en dev y `wsgi.py` en producción) y prepara el esquema solo:

- `db.create_all()` construye el esquema COMPLETO en una BD nueva — **los modelos
  son la fuente de verdad** y ya reflejan todas las columnas, tipos, índices y
  uniques que en su día añadieron los `.sql`.
- `schema_migrations` (tabla) registra qué `.sql` se han aplicado.
- **Baseline en el primer arranque**: si no hay tabla de registro, los `.sql`
  presentes se marcan como aplicados SIN ejecutarlos (create_all ya dejó el
  esquema al día). Esto evita re-ejecutar la 001 —cambio de tipo con `USING`—
  que sobre datos reales desplazaría las fechas.
- Los `.sql` que se añadan después (008+) se ejecutan una vez y se registran.
- Un advisory lock de Postgres serializa todo esto entre los workers de gunicorn.

Para un cambio de esquema en una BD ya desplegada: cambia el modelo Y añade un
`backend/migrations/00N_*.sql` idempotente (`... IF NOT EXISTS`) con su
`BEGIN/COMMIT`; `create_all` cubre las tablas nuevas, el `.sql` cubre los
`ALTER` sobre tablas existentes. `backend/scripts/backfill_library.py`
reconstruye la biblioteca desde los registros (idempotente).

## Despliegue (Railway)

- **Un solo servicio** vía `Dockerfile` multi-etapa: Node construye el Angular y
  Python (Flask) sirve la API **y** el SPA construido desde el mismo origen. Así
  la cookie del candado funciona sin CORS y solo hay una pieza que desplegar.
  Railway detecta el `Dockerfile` y lo usa. Arranca con `gunicorn wsgi:app` (no
  `run.py`, que es dev). El puerto se lee de `$PORT` en `backend/gunicorn.conf.py`
  (en Python, no en la shell): un `--bind 0.0.0.0:$PORT` en el comando llegaría a
  gunicorn con `$PORT` literal si Railway lo ejecuta en forma exec. **No añadir un
  `Procfile`**: Railway lo usaría por encima del CMD y reintroduciría ese fallo.
- **Flask sirve el SPA**: `_register_frontend()` en `app/__init__.py` sirve
  `FRONTEND_DIST` y hace fallback a `index.html` para el enrutado de Angular. En
  dev `FRONTEND_DIST` está vacío y el frontend lo sirve `ng serve` en :4200.
  `environment.ts` usa `apiUrl:'/api'` (relativo), que vale igual en dev (proxy)
  y en producción (mismo origen).
- **Postgres**: servicio gestionado de Railway; inyecta `DATABASE_URL`.
- **Variables obligatorias**: `ANTHROPIC_API_KEY`, `APP_ACCESS_TOKEN` (candado),
  `COOKIE_SECURE=1`, `APP_TIMEZONE`. `FRONTEND_DIST` y `UPLOAD_FOLDER` ya vienen
  fijadas en el `Dockerfile` (`/app/frontend_dist` y `/data/uploads`).
- **Fotos**: montar un **volumen** en `/data`. El disco del contenedor es
  efímero — sin volumen, las imágenes se borran en cada deploy. `UPLOAD_FOLDER`
  absoluto se usa tal cual; relativo se ancla a `backend/`.
- Auto-deploy: cada push a `main` despliega. Por eso el trabajo desde el móvil
  debería ir en rama → PR → merge cuando se ha verificado (ver más abajo).
- El `Dockerfile` se valida en local con `docker build` + `docker run` apuntando
  `DATABASE_URL` al Postgres del host (`host.docker.internal:5433`).

## Estructura

- `backend/app/models/` — `food_log`, `food_template`, `user_profile`,
  `weight_entry`, `activity`.
- `backend/app/services/` — la lógica de verdad vive aquí: `claude_service`
  (prompts + llamadas al LLM), `image_service`, `library_service`,
  `profile_service` + `profile_tool`, `targets_service`, `weight_service`,
  `activity_service`.
- `backend/app/routes/` — `food`, `library`, `profile`, `activity`.
- `frontend/src/app/` — componentes standalone. Pantallas: `/log` (hoy), `/add`,
  `/capture`, `/describe`, `/confirm`, `/library`, `/calendar`, `/profile`,
  `/profile/chat`, `/activity`. Servicios en `services/`, reutilizables en
  `shared/`.

## Convenciones

- **Estilos compartidos en `frontend/src/styles.scss`**; los `.scss` de
  componente solo llevan lo propio. El budget `anyComponentStyle` (4kb warn /
  6kb error) fuerza esa disciplina — si un build de producción falla por budget,
  extrae lo común a `styles.scss` en vez de subir el límite sin pensar.
- **Fechas en frontend**: usar `shared/date.utils.ts` (hora local, semana desde
  el lunes). **Nunca `toISOString()` para un `YYYY-MM-DD`**: convierte a UTC y
  desplaza el día.
- Comentarios y textos de UI en español.
- Verificar cambios con `npx ng build --configuration production` antes de dar
  algo por bueno.

## Trampas que ya costaron caras (no repetir)

- **Columnas JSON de SQLAlchemy**: al modificar un JSON (p. ej. `food_log.items`)
  hay que **copiar los dicts** (`[dict(i) for i in log.items]`) y llamar a
  `flag_modified(log, 'items')`. Si se mutan in situ, SQLAlchemy compara el valor
  nuevo con el cargado (ya mutado), no ve diferencia y **nunca emite el UPDATE**.
- **En `routes/food.py` no importar `time` desde `datetime`**: taparía el módulo
  `time` que usa `_cleanup_orphan_photos()` y rompe TODOS los guardados con un
  500 (después de haber hecho commit). Usar `datetime.min.time()`.
- **`app.config.ts` registra el locale `es` (`registerLocaleData`) y provee
  `LOCALE_ID`.** Sin eso, `{{ x | date:'EEEE' }}` lanza NG0701 y **la excepción
  aborta en silencio el resto del renderizado** (un `@for` deja de pintar a
  mitad y parece un fallo de datos). No añadir `:'':'es'` en las plantillas.
- **Prompts del LLM**: se construyen con funciones (`_image_prompt()` /
  `_text_prompt()`), **no con `.format()`** — el esquema JSON lleva llaves y
  `format()` las toma como campos (KeyError).
- **El entrenador (perfil) usa tool use con `tool_choice` forzado**
  (`services/profile_tool.py`), no JSON dentro del texto: con historial
  conversacional el modelo responde en prosa e ignora el esquema. El prefijo de
  respuesta del asistente NO sirve: `claude-sonnet-4-6` devuelve 400 "does not
  support assistant message prefill".
- **`free_notes` del perfil se SUSTITUYE, no se concatena**: el modelo reenvía el
  texto completo cada turno; acumular en el servidor repetía el mismo párrafo.
- **`.page` global lleva `min-height: 100vh`**; una pantalla a pantalla completa
  (el chat) debe anularlo con `min-height: 0` o el contenido queda bajo el menú
  fijo (72px).
- **Datos reales sin auth**: al ser usuario único, cualquier script de prueba con
  PATCH/DELETE golpea los datos reales del usuario. Usar una copia o revertir en
  transacción; nunca lanzar pruebas destructivas contra la BD viva.

## Autenticación (candado de acceso)

- App de **usuario único**: no hay tabla de usuarios ni contraseñas, solo un
  **secreto compartido** en `APP_ACCESS_TOKEN`. Vacío = candado DESACTIVADO (dev
  local sigue abierto sin tocar nada); definido = toda la API exige sesión.
- **Se valida por COOKIE httponly, no por cabecera** (`backend/app/auth.py`): las
  fotos se cargan con `<img src="/api/food/uploads/...">` y un `<img>` no puede
  mandar `Authorization`, pero sí la cookie. Se acepta además `Bearer` en
  cabecera para curl/scripts. Un `before_request` protege todo `/api/*` salvo
  `/api/auth/*` y `/health`.
- Endpoints: `GET /api/auth/status` (¿hace falta candado?, ¿ya autenticado?),
  `POST /api/auth/login` ({token} → cookie), `POST /api/auth/logout`.
- **Frontend**: `AuthService` + `authGuard` (protege las rutas, redirige a
  `/login`) + `authInterceptor` (ante 401 vuelve al login) +
  `login.component`. El diseño asume **mismo origen** front/back (el dev server
  proxya `/api`); en producción servir el SPA desde el mismo dominio que la API,
  o habría que pasar la cookie a `SameSite=None; Secure` + CORS con credenciales.
- **En producción (Railway) es OBLIGATORIO** poner `APP_ACCESS_TOKEN` y
  `COOKIE_SECURE=1`: sin candado, cualquiera con la URL gasta la clave de
  Anthropic vía `/analyze`.

## Decisiones de diseño (no deducibles del código)

- **La "cesta" multi-alimento se probó y se rechazó por complicada. No
  reintroducirla.** El flujo es: elegir/analizar UN alimento → `/confirm` (tipo
  de comida, fecha y hora editables, notas) → guardar → volver al día
  (`/log` si es hoy, si no `/calendar?mode=day&date=`).
- **Editar una plantilla de la biblioteca SÍ reescribe los días donde aparece**
  (`library_service.propagate_to_logs`). Borrarla NO borra el historial: solo
  pone `template_id: null` en los items. La foto solo se propaga a registros que
  no tenían una propia.
- La biblioteca se llena sola al guardar comida; identidad por `normalized_name`
  (índice único, deduplica). Los macros son SIEMPRE por 1 porción; el escalado lo
  aplican vista y backend, nunca se persiste ya multiplicado.
- **El prompt de análisis obliga a: identificar → decidir si es fuente
  compartida → estimar raciones → estimar gramos de UNA ración → solo entonces
  calcular nutrientes.** El error más caro era contar la fuente entera como una
  ración (1059 kcal reales → 560 tras corregir). No simplificar pidiendo las
  calorías directamente. Devuelve además `saturated_fat`, `salt`, rango min/max y
  un `assessment` que se guarda en `analysis` (log y plantilla).
- **Objetivos diarios desde el perfil** (`targets_service.py`): BMR (Mifflin-St
  Jeor) → gasto por actividad → ajuste por objetivo (lose −15%, recomp −5%,
  maintain 0, gain +12%) → proteína g/kg → grasa 27% de la energía → carbos el
  resto. `targets.basis` lo explica; `target_overrides` permite fijarlos a mano.
- **Las calorías de una actividad NO se restan del objetivo**: el objetivo ya
  incluye factor de actividad; restarlas sería contarlas dos veces. Son
  informativas hasta que haya Whoop (que medirá el gasto real del día).
- **Actividad: una sola tabla `activities` para manual y Whoop** (`source`,
  `external_id`). Las columnas encajan con `/v2/activity/workout` para que
  conectar la pulsera sea un mapeo, no una migración. Lo exclusivo de Whoop va en
  `metrics` (JSON).
- **Cinco familias de actividad con color fijo**
  (strength/racket/cardio/mobility/other): `#6C4DE0,#D97706,#0891B2,#DB2777,#4D7C0F`
  (paleta validada en claro y oscuro). El color nunca va solo: siempre con el
  nombre de la familia. `ActivityService.families` es la fuente única.
- **El peso NO se sobrescribe: hay histórico** (`weight_entries`, una fila por
  día). `user_profiles.weight_kg` es un caché del último valor (lo mantiene
  `_sync_current()`); si tocas la tabla por SQL, resincronízalo.
- `created_at` es `timestamptz`; el día natural se calcula con `APP_TIMEZONE`
  (Europe/Madrid), en SQL: `(created_at AT TIME ZONE :tz)::date`.
- `FLASK_DEBUG=0` a propósito: con `host=0.0.0.0` el depurador de Werkzeug sería
  RCE en la LAN.

## Flujo de trabajo (ramas y móvil)

`main` **auto-despliega a producción** (Railway): solo debe entrar en `main`
código verificado.

**Si trabajas desde una sesión sin entorno local (móvil o nube), NO puedes
verificar** —no hay Postgres con datos, ni `ANTHROPIC_API_KEY`, ni forma de
levantar la app o hacer capturas—, así que:

- Trabaja siempre en una **rama**, nunca directamente sobre `main`. Nombres:
  `movil/<tema>`, `feat/<tema>` o `fix/<tema>`.
- Commits pequeños y **abre un PR** hacia `main`. **No fundas el PR tú mismo.**
- En la descripción del PR di qué queda por verificar (build de producción,
  capturas, prueba con BD/foto reales).

**La verificación y el merge se hacen desde el escritorio**, donde sí hay
entorno: `git fetch`, `checkout` de la rama, levantar la app, build de
producción, capturas, `/analyze` con la clave real, y solo entonces `merge` a
`main` (que dispara el deploy).

```bash
# móvil / nube: rama sobre main al día → PR
git checkout main && git pull
git checkout -b movil/ajuste-perfil
# ...cambios...  →  commit  →  push  →  abrir PR (o `gh pr create`)
git push -u origin movil/ajuste-perfil

# escritorio: verificar y fundir
git fetch origin && git checkout movil/ajuste-perfil
# levantar + build de producción + capturas + probar con BD real
git checkout main && git merge --no-ff movil/ajuste-perfil && git push
```

Recomendado en GitHub: **proteger `main`** (Settings → Branches → require pull
request) para que ni un push accidental desde el móvil llegue directo a
producción.

## Pendiente

- **Integración con Whoop** (fases 0–5): bloqueada hasta tener cuenta de
  desarrollador y Client ID/Secret. La app ya está preparada (tabla `activities`,
  columnas compatibles). De Whoop se tomarán las **calorías gastadas**; las
  consumidas siguen saliendo del registro de comida.
- **Adherencia semanal** ("3 de 4 sesiones" contra los días de entrenamiento del
  perfil): aparcada hasta tener actividades reales acumuladas.
