@echo off
REM Deletes every simulated demo learner (emails ending in @demo.xeducation.test)
REM and everything linked to them. Real sign-ups are not touched.
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv.
  pause & exit /b 1
)
set PYTHONUTF8=1
"user-backend\venv\Scripts\python.exe" ml\seed_demo_data.py --remove
pause
