@echo off
REM Start the Scraper API Server
REM This script starts the FastAPI server on http://localhost:8000

echo Starting Universal Extraction Engine API Server...
echo Dashboard: http://localhost:8000
echo.

cd /d "%~dp0"

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start redis, postgres, elasticsearch if not running
echo Checking infrastructure...
docker-compose ps | find "postgres" >nul
if errorlevel 1 (
    echo Starting Docker containers (redis, postgres, elasticsearch)...
    docker-compose up -d postgres redis elasticsearch
    echo Waiting for services to be ready...
    timeout /t 10 /nobreak
)

REM Start the API server
echo.
echo Starting API server...
python main.py --api --api-host 0.0.0.0 --api-port 8000

pause
