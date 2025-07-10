@echo off
REM Setze den Pfad zu QGIS
set QGIS_PATH=C:\Program Files\QGIS 3.40.0

REM Füge QGIS-Binärverzeichnisse zum PATH hinzu
set PATH=%QGIS_PATH%\bin;%QGIS_PATH%\apps\qgis\bin;%QGIS_PATH%\apps\Qt5\bin;%PATH%

REM Setze PYTHONPATH
set PYTHONPATH=%QGIS_PATH%\apps\qgis\python;%PYTHONPATH%

@echo on
REM Kompiliere die Ressourcen
pyrcc5 -o resources.py resources.qrc

REM Kompiliere die Übersetzungen
"C:\OSGeo4W\apps\qt5\bin\lrelease.exe" i18n\de.ts -qm i18n\de.qm

@echo Compilation completed!
pause