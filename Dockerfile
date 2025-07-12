# 1. Basis-Image mit QGIS 3.40
FROM 3liz/qgis-platform:3.40

# 2. Root-Rechte für Systeminstallationen
USER root

# 3. System-Updates und Headless-X-Server (Xvfb) plus pytest installieren
RUN apt-get update \
 && apt-get install -y --no-install-recommends xvfb python3-pytest \
 && rm -rf /var/lib/apt/lists/*

# 4. Arbeitsverzeichnis im Container
WORKDIR /app

# 5. Plugin-Code und Tests kopieren
COPY . /app

# 6. Standard-Befehl: Tests über Xvfb „kopf­los“ ausführen
CMD ["xvfb-run", "-a", "pytest", "--maxfail=1", "--disable-warnings", "-q"]


