@echo off
net stop spooler /y
del /Q /F %systemroot%\System32\spool\PRINTERS\*
net start spooler