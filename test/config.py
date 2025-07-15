import configparser
import os
import sys
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / 'test_config.ini'

parser = configparser.ConfigParser()
parser.read(CONFIG_FILE)

QGIS_PREFIX_PATH = parser.get('qgis', 'prefix_path', fallback=r'C:\\Program Files\\QGIS 3.40.0')

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def apply_qgis_environment():
    """Apply QGIS environment variables and sys.path entries."""
    os.environ.setdefault('QGIS_PREFIX_PATH', QGIS_PREFIX_PATH)
    os.environ.setdefault('PYTHONPATH', str(Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python'))
    paths = [
        Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python',
        Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python' / 'plugins',
        Path(QGIS_PREFIX_PATH) / 'apps' / 'Python312' / 'Lib' / 'site-packages',
    ]
    for p in paths:
        p_str = str(p)
        if os.path.exists(p_str) and p_str not in sys.path:
            sys.path.insert(0, p_str)
