@echo off
REM ==========================================================================
REM  X Education - stop every server started by start-all.bat
REM ==========================================================================
setlocal EnableExtensions
echo Stopping X Education servers...

REM 1) Close the launcher windows (and everything running inside them)
taskkill /FI "WINDOWTITLE eq XEDU*" /T /F >nul 2>&1

REM 2) Safety net: kill anything still listening on our ports
for %%P in (8000 8001 5173 5174) do (
  for /f "tokens=5" %%A in ('netstat -ano ^| findstr /r /c:":%%P .*LISTENING"') do (
    echo   Killing PID %%A on port %%P
    taskkill /PID %%A /T /F >nul 2>&1
  )
)

echo Done. All ports 8000 / 8001 / 5173 / 5174 are free.
timeout /t 3 >nul
