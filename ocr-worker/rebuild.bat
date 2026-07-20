@echo off
setlocal
cd /d "%~dp0.." || exit /b 1
call docker compose up -d --build ocr
