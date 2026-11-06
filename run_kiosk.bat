@echo off
title Perpetual Bistro - Web Ordering Kiosk Dashboard
cd /d "%~dp0"
echo ==================================================================
echo   Starting Perpetual Bistro Web Tablet Dashboard...
echo ==================================================================
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3.14 web_dashboard.py --port 8000
) else (
    python web_dashboard.py --port 8000
)
pause
