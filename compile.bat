@echo off
REM Compiles the German translation (i18n\IBTool_de.ts -> i18n\IBTool_de.qm).
REM Adjust LRELEASE if your OSGeo4W installation lives elsewhere.
REM The release ZIP is built with: python scripts\create_release_zip.py
set LRELEASE=C:\OSGeo4W\apps\qt5\bin\lrelease.exe

@echo on
"%LRELEASE%" i18n\IBTool_de.ts -qm i18n\IBTool_de.qm

@echo Compilation completed!
pause
