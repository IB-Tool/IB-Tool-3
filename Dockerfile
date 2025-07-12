# 1. Basis-Image mit QGIS 3.40
FROM 3liz/qgis-platform:3.40

# 2. Root-Rechte für Systeminstallationen
USER root

# 3. System-Updates, Headless-X-Server und Python-Abhängigkeiten installieren
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    xvfb \
    python3-pytest \
    python3-numpy \
    python3-pandas \
    python3-matplotlib \
    python3-scipy \
    python3-sklearn \
    python3-networkx \
    python3-geopandas \
 && rm -rf /var/lib/apt/lists/*

# 4. Arbeitsverzeichnis im Container
WORKDIR /app

# 5. Plugin-Code und Tests kopieren
COPY . /app

# 6. Umgebungsvariablen für headless mode setzen
ENV QT_QPA_PLATFORM=offscreen

# 7. Finale Test-Ausführung
CMD ["python3", "-m", "pytest", "test/", "-v", "--tb=short"]