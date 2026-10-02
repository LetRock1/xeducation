@echo off
REM CLOSED LOOP: retrain both models on real outcomes recorded by the website.
REM Each new model replaces the live one only if it is better on held-out real data.
REM   retrain-model.bat                   normal (outcome window 14 days)
REM   retrain-model.bat --window-days 1   demo: count outcomes after 1 day
REM   retrain-model.bat --dry-run         report only
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv.
  pause & exit /b 1
)
set PYTHONUTF8=1
echo ==== Lead-scoring model ====
"user-backend\venv\Scripts\python.exe" ml\retrain_from_live.py %*
echo.
echo ==== Next-best-action model ====
"user-backend\venv\Scripts\python.exe" ml\retrain_nba_from_live.py %*
pause
