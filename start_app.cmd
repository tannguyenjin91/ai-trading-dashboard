@echo off
title VN AI Trader
echo =======================================
echo     Starting VN AI Trader System
echo =======================================

cd /d "%~dp0"

:: Set Python encoding for Windows to prevent console emoji errors
set PYTHONIOENCODING=utf-8

:: Step 1: Start the Frontend in a new window
echo Starting React Frontend...
start "VN AI Trader - Frontend" cmd /c "cd frontend && npm run dev"

:: Step 2: Start the Backend in this window
echo Starting FastAPI Backend...
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
pause
