@echo off
REM Re-runs the research experiments and writes ml\results\*.md / *.json (+ figures).
REM Needs ml\data\Leads.csv and ml\data\hillstrom.csv. Takes about 30 minutes in total.
REM   run-experiments.bat            all four
REM   run-experiments.bat quick      only the two real-data experiments (about 8 minutes)
cd /d "%~dp0"
if not exist "user-backend\venv\Scripts\python.exe" (
  echo Run start-all.bat once first - it creates the backend venv and trains the models.
  pause & exit /b 1
)
set PYTHONUTF8=1
set "PY=user-backend\venv\Scripts\python.exe"
"%PY%" -c "import matplotlib" >nul 2>&1
if errorlevel 1 echo [INFO] matplotlib is not installed - figures are skipped. To get them: "%PY%" -m pip install matplotlib
echo.
echo ==== 1/4 Lead scoring on real data (X Education, 9,240 leads) ====
"%PY%" ml\experiments\real_benchmark.py
echo.
echo ==== 2/4 Next-best-action on a real randomized experiment (Hillstrom, 64,000 customers) ====
"%PY%" ml\experiments\hillstrom_uplift.py
if /i "%~1"=="quick" goto :done
echo.
echo ==== 3/4 Robustness when our assumptions are wrong (simulation, about 15 minutes) ====
"%PY%" ml\experiments\nba_robustness.py
echo.
echo ==== 4/4 How-to-convert tips: validity, effort, causal gap (simulation) ====
"%PY%" ml\experiments\recourse_eval.py
:done
echo.
echo Results: ml\results\  (open the .md files; figures in ml\results\figures)
pause
