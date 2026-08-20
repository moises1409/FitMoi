# Arranca PostgreSQL con Docker y el backend Flask
$projectRoot = $PSScriptRoot

# --- Verificar Docker Desktop ---
docker info 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ATENCION: Docker Desktop no esta en ejecucion." -ForegroundColor Red
    Write-Host "Abre Docker Desktop, espera la ballena en la barra de tareas y vuelve a ejecutar." -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "Iniciando PostgreSQL..." -ForegroundColor Green
docker-compose -f "$projectRoot\docker-compose.yml" up -d postgres

# Esperar a que el contenedor responda (hasta 30s)
Write-Host "Esperando a que PostgreSQL este listo..." -ForegroundColor Yellow
$ready = $false
for ($i = 1; $i -le 15; $i++) {
    Start-Sleep -Seconds 2
    $result = docker exec fitmoi_db pg_isready -U fitmoi -d fitmoi -p 5432 2>$null
    if ($LASTEXITCODE -eq 0) {
        $ready = $true
        break
    }
    Write-Host "  Intento $i/15..." -ForegroundColor DarkGray
}

if (-not $ready) {
    Write-Host "Timeout esperando PostgreSQL. Prueba a ejecutar el script de nuevo." -ForegroundColor Red
    exit 1
}
Write-Host "PostgreSQL listo." -ForegroundColor Green

# --- Backend Python ---
$backendDir = Join-Path $projectRoot "backend"
Set-Location $backendDir
$venvPath = Join-Path $backendDir ".venv"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creando entorno virtual Python..." -ForegroundColor Yellow
    py -m venv .venv
}

Write-Host "Instalando/verificando dependencias..." -ForegroundColor Yellow
& "$venvPath\Scripts\pip.exe" install -r requirements.txt --quiet

Write-Host ""
Write-Host "Iniciando Flask en http://0.0.0.0:5000" -ForegroundColor Green
Write-Host "Movil: http://192.168.1.109:5000" -ForegroundColor Cyan
Write-Host ""

& "$venvPath\Scripts\python.exe" run.py
