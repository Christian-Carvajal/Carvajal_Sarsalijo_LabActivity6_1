@echo off
title Perpetual Bistro - Web Ordering Kiosk Dashboard
cd /d "%~dp0"
echo ==================================================================
echo   Starting Perpetual Bistro Web Tablet Dashboard...
echo ==================================================================
python web_dashboard.py --port 8000
pause
