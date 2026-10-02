@echo off
REM CLOSED LOOP: retrain on real outcomes (purchases) recorded by the website.
REM The new model replaces the live one only if it is better on real users.
REM   retrain-model.bat                   normal (outcome window 14 days)
REM   retrain-model.bat --window-days 1   demo: label outcomes after 1 day
REM   retrain-model.bat --dry-run         report only
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv.
  pause & exit /b 1
)
set PYTHONUTF8=1
"user-backend\venv\Scripts\python.exe" ml\retrain_from_live.py %*
pause
