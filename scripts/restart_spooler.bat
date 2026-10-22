@echo off
setlocal
net stop spooler /y
if errorlevel 1 exit /b 1
net start spooler
exit /b %errorlevel%
