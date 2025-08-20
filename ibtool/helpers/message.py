from qgis.core import Qgis

from qgis.utils import QgsMessageLog

def msg(message, level=Qgis.Info):
    if not isinstance(message, str):
        message = str(message)
    QgsMessageLog.logMessage(message, 'Meldungen', level=level)
