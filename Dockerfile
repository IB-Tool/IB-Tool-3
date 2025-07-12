# 1. Basis-Image mit QGIS 3.40
FROM 3liz/qgis-platform:3.40

# 2. Arbeitsverzeichnis im Container
WORKDIR /app

# 3. Plugin-Code und Tests kopieren
COPY . /app

# 4. Test-Framework installieren
RUN pip install --no-cache-dir pytest

# 5. Standard-Befehl: Tests ausführen
CMD ["pytest", "--maxfail=1", "--disable-warnings", "-q"]
