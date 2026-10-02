@echo off
REM Adds 400 SIMULATED learners with 6 weeks of history, so Model health, the
REM next-best-action report, Today's actions and retrain-model.bat can be demonstrated.
REM All of them have emails ending in @demo.xeducation.test (never mailed) and are
REM marked "simulated" in the dashboard. Remove them with remove-demo-data.bat.
REM   seed-demo-data.bat            400 learners
REM   seed-demo-data.bat --n 800    more learners
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv and trains the models.
  pause & exit /b 1
)
set PYTHONUTF8=1
"user-backend\venv\Scripts\python.exe" ml\seed_demo_data.py %*
pause
