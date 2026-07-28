@echo off
chcp 65001 >nul
setlocal
set "ROOT=%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_demo.ps1"
set "RESULT=%ERRORLEVEL%"
echo.
if not "%RESULT%"=="0" (
  echo One or more components could not be started. Review the messages above.
) else (
  echo Demo startup completed successfully.
)
echo You may close this window; the demo services will keep running.
pause
exit /b %RESULT%
