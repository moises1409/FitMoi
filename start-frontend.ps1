# Arranca el frontend Angular accesible desde la red local (movil)
Write-Host "Iniciando frontend Angular en http://0.0.0.0:4200 ..." -ForegroundColor Green
Write-Host "Accede desde tu movil en: http://<IP-DE-TU-PC>:4200" -ForegroundColor Cyan

Set-Location frontend
npx ng serve --host 0.0.0.0 --port 4200 --proxy-config proxy.conf.json --open
