@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
git pull origin main
call docker compose down
call docker compose up -d --build
