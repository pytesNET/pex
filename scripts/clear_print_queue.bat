@echo off
setlocal
if /I not "%~1"=="--confirm-clear" (
    echo This command deletes ALL pending Windows print jobs. Pass --confirm-clear explicitly.
    exit /b 2
)
net stop spooler /y
if errorlevel 1 exit /b 1
del /Q /F "%systemroot%\System32\spool\PRINTERS\*"
set "CLEAR_CODE=%errorlevel%"
net start spooler
if errorlevel 1 exit /b 1
exit /b %CLEAR_CODE%
