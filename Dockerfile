# 1. Basis-Image mit QGIS 3.40
FROM 3liz/qgis-platform:3.40

# 2. Root-Rechte für Systeminstallationen
USER root


# 3. System-Updates, Headless-X-Server und Python-Abhängigkeiten installieren
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    xvfb \
    python3-pytest \
    python3-pytest-cov \
    python3-coverage \
    python3-numpy \
    python3-pandas \
    python3-matplotlib \
    python3-scipy \
    python3-sklearn \
    python3-networkx \
    python3-geopandas \
    python3-gdal \
    gdal-bin \
    python3-psycopg2 \
    python3-shapely \
    python3-fiona \
 && rm -rf /var/lib/apt/lists/*

# 4. Arbeitsverzeichnis im Container
WORKDIR /app

# 5. Plugin-Code und Tests kopieren
COPY . /app

# 6. Umgebungsvariablen für headless mode und Processing setzen
ENV QT_QPA_PLATFORM=offscreen
ENV QGIS_PREFIX_PATH=/usr
ENV PYTHONPATH=/usr/share/qgis/python:/usr/share/qgis/python/plugins:$PYTHONPATH
ENV QGIS_PLUGINPATH=/usr/share/qgis/python/plugins

# 7. QGIS Processing Provider explizit initialisieren
RUN python3 -c "\
import sys; \
sys.path.insert(0, '/usr/share/qgis/python'); \
sys.path.insert(0, '/usr/share/qgis/python/plugins'); \
from qgis.core import QgsApplication; \
app = QgsApplication([], False); \
app.setPrefixPath('/usr', True); \
app.initQgis(); \
import processing; \
from processing.core.Processing import Processing; \
Processing.initialize(); \
print('Processing erfolgreich initialisiert'); \
app.exitQgis()"

# 8. Finale Test-Ausführung
CMD ["python3", "-m", "pytest", "test/", "-v", "--tb=short", "--cov=ibtool", "--cov-report=xml", "--cov-report=html"]
