@echo off
title Book Recommendation Server Launcher
color 0a

echo ===========================================
echo   Starting BookRec Flask Server
echo ===========================================

:: تشغيل MySQL إذا لم يكن يعمل
echo.
echo Checking MySQL service...
net start MySQL80 >nul 2>&1
if %errorlevel%==0 (
    echo MySQL service started successfully.
) else (
    echo MySQL service is already running.
)

:: الانتقال إلى مجلد المشروع
cd /d "%~dp0"

:: تفعيل البيئة الافتراضية
echo.
echo Activating virtual environment...
call venv\Scripts\activate

:: تشغيل السيرفر
echo.
echo Starting Flask server...
echo -------------------------------------------
set FLASK_APP=flask_book_recommendation.app:create_app
python -m flask run

:: عند الإيقاف
echo.
echo Flask server stopped.
pause
