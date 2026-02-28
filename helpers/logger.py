import logging
import os
import time
from qgis.core import Qgis, QgsMessageLog
from .message import msg


class Logger:
    """Singleton logger that writes to the QGIS message panel, a log file, and a message box.

    On first instantiation the log file is created under ``log_dir``.
    Use :meth:`set_message_box` to attach a UI widget for in-dialog output.
    """

    _instance = None
    message_box = None
    file_handler = None
    log_level = logging.INFO  # default log level
    log_dir = None  # directory for log files

    def __new__(cls) -> "Logger":
        if cls._instance is None:
            cls._instance = super(Logger, cls).__new__(cls)
            cls._initialize_logging()
        return cls._instance

    @classmethod
    def _initialize_logging(cls) -> None:
        """Initialise the log file and configure the Python logging handler."""
        start_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        if not cls.log_dir:
            cls.log_dir = os.path.join(os.getcwd(), "logs")  # default: current working directory
        msg(cls.log_dir)
        os.makedirs(cls.log_dir, exist_ok=True)
        log_filename = os.path.join(cls.log_dir, f"logfile_{start_time}.txt")

        cls.file_handler = logging.FileHandler(log_filename, mode='a')
        cls.file_handler.setLevel(logging.INFO)  # log everything to file
        formatter = logging.Formatter('%(levelname)s %(asctime)s - %(message)s', datefmt='%H:%M:%S')
        cls.file_handler.setFormatter(formatter)

        # configure logging
        logging.basicConfig(level=cls.log_level, handlers=[cls.file_handler])
        cls.log(f"Logger initialisiert. Logdatei: {log_filename}", level="INFO")

    @classmethod
    def set_message_box(cls, message_box: object) -> None:
        """Attach a UI message box widget for in-dialog log output.

        Args:
            message_box: A QPlainTextEdit (or compatible) widget to receive log lines.
        """
        cls.message_box = message_box

    @classmethod
    def set_log_dir(cls, log_dir: str) -> None:
        """Change the log directory and start a new log file there.

        Closes the current file handler, updates ``log_dir``, and opens a
        fresh log file in the new location.

        Args:
            log_dir: Absolute or relative path to the desired log directory.
        """
        if cls.file_handler:
            cls.file_handler.close()
            logging.getLogger().removeHandler(cls.file_handler)
            cls.file_handler = None
        cls.log_dir = log_dir
        cls._initialize_logging()

    @classmethod
    def set_log_level(cls, level: str) -> None:
        """Set the global log level filter.

        Args:
            level: One of ``'INFO'``, ``'WARNING'``, ``'CRITICAL'``, ``'SUCCESS'``.

        Raises:
            ValueError: If ``level`` is not a recognised log level name.
        """
        log_levels = {
            'INFO': logging.INFO,
            'WARNING': logging.WARNING,
            'CRITICAL': logging.CRITICAL,
            'SUCCESS': logging.DEBUG,  # SUCCESS maps to DEBUG level
        }
        msg(level)
        if level not in log_levels:
            raise ValueError(
                f"Invalid log level: '{level}'. "
                f"Available levels: {', '.join(log_levels.keys())}"
            )

        cls.log_level = log_levels[level]
        logging.getLogger().setLevel(cls.log_level)  # update file log level
        cls.log(f"Log-Level auf {level} gesetzt.", level="WARNING")

    @classmethod
    def log(cls, message: object, level: str = "WARNING") -> None:
        """Emit a log message to the file, the UI message box, and the QGIS message log.

        The message is only emitted if ``level`` meets or exceeds the configured
        threshold (set via :meth:`set_log_level`).

        Args:
            message: The message to log. Non-string values are converted with ``str()``.
            level: Severity — one of ``'INFO'``, ``'WARNING'``, ``'CRITICAL'``,
                ``'SUCCESS'``. Defaults to ``'WARNING'``.

        Raises:
            ValueError: If ``level`` is not a recognised log level name.
        """
        log_levels = {
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "CRITICAL": logging.CRITICAL,
            "SUCCESS": logging.DEBUG,  # SUCCESS maps to DEBUG level
        }

        if level not in log_levels:
            raise ValueError(
                f"Invalid log level: '{level}'. "
                f"Available levels: {', '.join(log_levels.keys())}"
            )

        logger_level = log_levels[level]

        # only emit if message level meets or exceeds the configured threshold
        if cls.log_level <= logger_level:
            if not isinstance(message, str):
                message = str(message)

            # write to log file
            logging.getLogger().log(logger_level, message)

            # display in message box
            if cls.message_box:
                try:
                    cls.message_box.appendPlainText(f"{level}: {message}")
                except RuntimeError:
                    # Qt widget was deleted (e.g. dialog closed in test teardown)
                    cls.message_box = None
                    msg(f"{level}: {message}")
            else:
                msg(f"{level}: {message}")

            # forward to QGIS message log
            QgsMessageLog.logMessage(message, "IBTool", level=cls._qgis_level(level))

    @staticmethod
    def _qgis_level(level: str) -> int:
        """Map an IBTool log level string to the corresponding QGIS message level.

        Args:
            level: IBTool level string — ``'INFO'``, ``'WARNING'``, ``'CRITICAL'``,
                or ``'SUCCESS'``.

        Returns:
            A ``Qgis.MessageLevel`` integer constant. Falls back to ``Qgis.Info``
            for unknown level strings.
        """
        mapping = {
            'INFO': Qgis.Info,
            'WARNING': Qgis.Warning,
            'CRITICAL': Qgis.Critical,
            'SUCCESS': Qgis.Success,
        }
        return mapping.get(level, Qgis.Info)

    @classmethod
    def close_logger(cls) -> None:
        """Close the file handler and remove it from the root logger."""
        if cls.file_handler:
            cls.file_handler.close()
            logging.getLogger().removeHandler(cls.file_handler)
            cls.log("Logger geschlossen.", level="INFO")
