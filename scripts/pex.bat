@echo off
setlocal
cd /d "%~dp0\.."
call .venv\Scripts\python.exe src\pex\__main__.py --admin %*
echo.
echo [ENDE]
pause
endlocal