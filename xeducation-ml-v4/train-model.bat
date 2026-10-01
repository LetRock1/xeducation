@echo off
REM Regenerates the synthetic dataset (if missing) and retrains the lead-scoring
REM model with the backend's own Python, so the versions always match.
REM The running backend picks up the new model automatically.
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv.
  pause & exit /b 1
)
set PYTHONUTF8=1
"user-backend\venv\Scripts\python.exe" ml\train_model.py %*
pause
