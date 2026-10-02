@echo off
REM Trains both models with the backend's own Python (versions always match):
REM   1. lead-scoring model      -> user-backend\ml_models\lead_model.pkl
REM   2. next-best-action model  -> user-backend\ml_models\nba_model.pkl
REM The running backend picks up new models automatically.
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv.
  pause & exit /b 1
)
set PYTHONUTF8=1
"user-backend\venv\Scripts\python.exe" ml\train_model.py %*
if errorlevel 1 ( pause & exit /b 1 )
"user-backend\venv\Scripts\python.exe" ml\train_uplift.py
pause
