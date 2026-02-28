"""Thin wrapper for forwarding messages to the QGIS message log."""
from qgis.core import Qgis
from qgis.utils import QgsMessageLog


def msg(message: object, level: int = Qgis.Info) -> None:
    """Forward a message to the QGIS message log panel.

    Args:
        message: The message to log. Non-string values are converted with ``str()``.
        level: QGIS message level (e.g. ``Qgis.Info``, ``Qgis.Warning``).
            Defaults to ``Qgis.Info``.
    """
    if not isinstance(message, str):
        message = str(message)
    QgsMessageLog.logMessage(message, 'Meldungen', level=level)
