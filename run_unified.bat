@echo off
echo ========================================================
echo 🚀 Starting Unified AI Recommendation System
echo ========================================================
echo.
echo [1] Activating Virtual Environment...
call venv\Scripts\activate
if %errorlevel% neq 0 (
    echo ⚠️ Virtual environment not found. Trying to run with global python...
)

echo.
echo [2] Starting Unified Server (FastAPI + Flask)...
echo    - API Port: 5000 (proxied)
echo    - Web Port: 5000
echo.
echo ⚠️ PLEASE WAIT for the server to start...
echo.

python unified_server.py

pause
