import logging
import os
import time
from qgis.core import Qgis, QgsMessageLog
from .message import msg

class Logger:
    """Singleton-Logger, um Nachrichten im Nachrichtenfenster und in einer Logdatei auszugeben."""
    _instance = None
    message_box = None
    file_handler = None
    log_level = logging.INFO  # Standard-Log-Level
    log_dir = None  # Directory for log files

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._initialize_logging()
        return cls._instance

    @classmethod
    def _initialize_logging(cls):
        """Initialisiert die Logdatei und die Logging-Konfiguration."""
        startzeit = time.strftime("%Y-%m-%d_%H-%M-%S")
        if not cls.log_dir:
            cls.log_dir = os.path.join(os.getcwd(), "logs")  # Standard ist das aktuelle Verzeichnis
        msg(cls.log_dir)
        os.makedirs(cls.log_dir, exist_ok=True)
        log_filename = os.path.join(cls.log_dir, f"logfile_{startzeit}.txt")

        cls.file_handler = logging.FileHandler(log_filename, mode='a')
        cls.file_handler.setLevel(logging.INFO)  # Log alles in die Datei
        formatter = logging.Formatter('%(levelname)s %(asctime)s - %(message)s', datefmt='%H:%M:%S')
        cls.file_handler.setFormatter(formatter)

        # Logging-Konfiguration
        logging.basicConfig(level=cls.log_level, handlers=[cls.file_handler])
        cls.log(f"Logger initialisiert. Logdatei: {log_filename}", level="INFO")

    @classmethod
    def set_message_box(cls, message_box):
        """Setzt die Referenz auf das Nachrichtenfenster."""
        cls.message_box = message_box

    @classmethod
    def set_log_level(cls, level):
        """Setzt das globale Log-Level."""
        log_levels = {
            'DEBUG': logging.DEBUG,
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'CRITICAL': logging.CRITICAL,
        }
        msg(level)
        if level not in log_levels:
            raise ValueError(f"Ungültiger Log-Level: {level}. Verfügbare Levels: {', '.join(log_levels.keys())}")

        cls.log_level = log_levels[level]
        logging.getLogger().setLevel(cls.log_level)  # Setze das Log-Level für die Datei
        cls.log(f"Log-Level auf {level} gesetzt.", level="INFO")

    @classmethod
    def set_log_dir(cls, directory):
        """Legt das Verzeichnis für Logdateien fest und initialisiert neu."""
        cls.log_dir = directory
        if cls.file_handler:
            cls.file_handler.close()
            logging.getLogger().removeHandler(cls.file_handler)
        cls._initialize_logging()

    @classmethod
    def log(cls, message, level="INFO"):
        """
        Gibt eine Nachricht im Nachrichtenfenster aus und schreibt sie in die Logdatei.
        :param message: Die zu loggende Nachricht.
        :param level: Das Log-Level ('INFO', 'WARNING', 'DEBUG', 'ERROR', 'CRITICAL').
        """
        log_levels = {
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "CRITICAL": logging.CRITICAL,
            'SUCCESS': logging.DEBUG
        }

        if level not in log_levels:
            raise ValueError(f"Ungültiger Log-Level: {level}. Verfügbare Levels: {', '.join(log_levels.keys())}")

        logger_level = log_levels[level]

        # Nachricht nur ausgeben, wenn sie dem aktuellen Log-Level entspricht
        if logger_level >= cls.log_level:
            # Convert message to string if it is not already
            if not isinstance(message, str):
                message = str(message)

            # Login-Datei schreiben
            logging.getLogger().log(logger_level, message)

            # Nachricht im Nachrichtenfenster anzeigen
            if cls.message_box:
                cls.message_box.appendPlainText(f"{level}: {message}")
            else:
                msg(f"{level}: {message}")

            # Nachricht in die QGIS-Meldungen ausgeben
            QgsMessageLog.logMessage(message, "IBTool", level=cls._qgis_level(level))

    @staticmethod
    def _qgis_level(level):
        """Konvertiert Python-Log-Level zu QGIS-Log-Level."""
        mapping = {
            'INFO': Qgis.Info,
            'WARNING': Qgis.Warning,
            'CRITICAL': Qgis.Critical,
            'SUCCESS':Qgis.Success,
        }
        return mapping.get(level, Qgis.Info)

    @classmethod
    def close_logger(cls):
        """Schließt den File-Handler des Loggers und entfernt ihn."""
        if cls.file_handler:
            cls.file_handler.close()
            logging.getLogger().removeHandler(cls.file_handler)
            cls.log("Logger geschlossen.", level="INFO")