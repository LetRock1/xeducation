@echo off
REM ==========================================================================
REM  X Education CRM - start everything (stop-all.bat stops it)
REM  Put this file in the project root (next to user-backend, marketing-backend,
REM  user-frontend, marketing-frontend) and double-click it.
REM ==========================================================================

REM ---- Re-open inside a window that NEVER auto-closes, so errors stay visible
if not "%XEDU_LAUNCHED%"=="1" (
  set XEDU_LAUNCHED=1
  start "X Education Launcher" cmd /k ""%~f0""
  exit /b
)

setlocal EnableExtensions
cd /d "%~dp0"
set "ROOT=%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo ================================================
echo    X EDUCATION CRM - starting
echo ================================================
echo Running from: %ROOT%
echo.

REM ---- Find a real Python (skip the Microsoft Store stub) -------------------
set "PY="
py -3 --version >nul 2>&1 && set "PY=py -3"
if not defined PY (
  python --version >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [ERROR] No working Python found.
  echo         Install Python 3.11 or 3.12 from python.org and tick "Add python.exe to PATH".
  echo         If typing "python" opens the Microsoft Store, turn off the alias in:
  echo         Settings ^> Apps ^> Advanced app settings ^> App execution aliases.
  goto :fail
)
echo Using Python:
%PY% --version

where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js / npm not found. Install Node 20 LTS from nodejs.org, then reopen this.
  goto :fail
)
echo Using Node:
node --version

REM ---- Check folder layout --------------------------------------------------
set "MISSING="
for %%D in (user-backend marketing-backend user-frontend marketing-frontend) do (
  if not exist "%ROOT%%%D\" (
    echo [ERROR] Folder "%%D" not found next to this script.
    set "MISSING=1"
  )
)
if defined MISSING (
  echo.
  echo         This .bat must sit in the SAME folder that contains those 4 folders.
  echo         Right now it is in: %ROOT%
  goto :fail
)

REM ---- Setup --------------------------------------------------------------
call :setup_backend user-backend
if errorlevel 1 goto :fail
call :setup_backend marketing-backend
if errorlevel 1 goto :fail
call :setup_frontend user-frontend
if errorlevel 1 goto :fail
call :setup_frontend marketing-frontend
if errorlevel 1 goto :fail

REM ---- Course catalogue for the backend (prices etc. from courses.js) -----
pushd "%ROOT%"
node tools\sync-catalog.mjs
popd

REM ---- Models and starting history: only what is missing ------------------
REM  First start: trains the lead model and the next-best-action model (about 30 s)
REM  and creates 6 simulated months of history (about 5-10 minutes, once).
pushd "%ROOT%"
"user-backend\venv\Scripts\python.exe" ml\first_run.py
if errorlevel 1 echo [WARN] First-run setup reported a problem - see the lines above.
popd

REM ---- Launch -------------------------------------------------------------
echo.
echo ==== Launching servers ====

start "XEDU user-backend :8000" /D "%ROOT%user-backend" cmd /k "venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"

echo Waiting for user-backend (it creates the shared database)...
set /a TRIES=0
:wait_loop
set /a TRIES+=1
powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health ^| Out-Null; exit 0}catch{exit 1}" >nul 2>&1
if not errorlevel 1 goto :backend_ready
if %TRIES% GEQ 40 goto :backend_slow
timeout /t 1 /nobreak >nul
goto :wait_loop

:backend_slow
echo [WARN] user-backend has not answered yet - check its window for errors.
echo        Starting the rest anyway.
:backend_ready

start "XEDU marketing-backend :8001"  /D "%ROOT%marketing-backend"  cmd /k "venv\Scripts\python.exe -m uvicorn main:app --reload --port 8001"
start "XEDU user-frontend :5173"      /D "%ROOT%user-frontend"      cmd /k "npm run dev"
start "XEDU marketing-frontend :5174" /D "%ROOT%marketing-frontend" cmd /k "npm run dev"

timeout /t 6 /nobreak >nul
start "" http://localhost:5173
start "" http://localhost:5174

echo.
echo ================================================
echo   All 4 servers launched in separate windows:
echo     User site          http://localhost:5173
echo     Marketing dash     http://localhost:5174
echo     User API docs      http://localhost:8000/docs
echo     Marketing API docs http://localhost:8001/docs
echo   If a page does not load, look at that server's window for the error.
echo   Run stop-all.bat to shut everything down.
echo ================================================
goto :eof


REM ==========================================================================
:setup_backend
set "DIR=%ROOT%%~1"
echo.
echo ==== %~1 ====
if exist "%DIR%\venv\Scripts\python.exe" goto :venv_ok
echo Creating virtual environment...
%PY% -m venv "%DIR%\venv"
if errorlevel 1 (
  echo [ERROR] Could not create venv in %~1
  exit /b 1
)
:venv_ok
fc /b "%DIR%\requirements.txt" "%DIR%\venv\.installed-requirements.txt" >nul 2>&1
if not errorlevel 1 (
  echo Requirements already installed - skipping.
  goto :env_check
)
echo Installing Python requirements - this takes a few minutes the first time...
"%DIR%\venv\Scripts\python.exe" -m pip install --upgrade pip
"%DIR%\venv\Scripts\python.exe" -m pip install -r "%DIR%\requirements.txt"
if errorlevel 1 (
  echo [ERROR] pip install failed for %~1 - see the messages above.
  exit /b 1
)
copy /y "%DIR%\requirements.txt" "%DIR%\venv\.installed-requirements.txt" >nul
:env_check
if not exist "%DIR%\.env" echo [WARN] %~1\.env is missing - defaults will be used.
exit /b 0


REM ==========================================================================
:setup_frontend
set "DIR=%ROOT%%~1"
echo.
echo ==== %~1 ====
if not exist "%DIR%\node_modules\" goto :do_npm_install
fc /b "%DIR%\package.json" "%DIR%\node_modules\.installed-package.json" >nul 2>&1
if errorlevel 1 goto :do_npm_install
echo node_modules up to date - skipping.
exit /b 0

:do_npm_install
echo Running npm install...
pushd "%DIR%"
call npm install
if errorlevel 1 (
  popd
  echo [ERROR] npm install failed for %~1 - see the messages above.
  exit /b 1
)
copy /y "package.json" "node_modules\.installed-package.json" >nul
popd
exit /b 0


REM ==========================================================================
:fail
echo.
echo [FAILED] Setup stopped. Read the [ERROR] line above, or copy this whole
echo          window's text and paste it to Claude.
goto :eof
