@echo off
setlocal

cd /d "%~dp0\.."
call .venv\Scripts\activate
pex ui %*

echo.
echo [ENDE]
#pause
endlocal
exit /b %CODE%