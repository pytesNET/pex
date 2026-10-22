@echo off
setlocal
cd /d "%~dp0\.."
".venv\Scripts\python.exe" -m pex ui %*
set "CODE=%errorlevel%"
if not "%CODE%"=="0" pause
exit /b %CODE%
