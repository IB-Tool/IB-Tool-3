#!/usr/bin/env python3
"""CLI entry point to run IBTool headlessly.

Usage:
    python3 scripts/run_cli.py /path/to/config.ini

The configuration file should contain keys matching the dialog widgets of
:class:`IBToolDialog`. Values are assigned by attribute name across all
sections. Example:

    [paths]
    HuPath = /data/hu.shp
    RnPath = /data/rn.shp
    OutputPath = /tmp/result.gpkg

    [params]
    MinOverlapBlocksBox = 5
    PartLogBox = true

"""
import logging
import sys
import configparser

from test.config import apply_qgis_environment
from test.utilities import get_qgis_app


def add_stdout_logging():
    """Ensure root logger prints to stdout as well as files."""
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        fmt = logging.Formatter('%(levelname)s %(asctime)s - %(message)s',
                                datefmt='%H:%M:%S')
        handler.setFormatter(fmt)
        root.addHandler(handler)


def populate_dialog(dialog, config):
    """Populate dialog widgets from ini configuration."""
    for section in config.sections():
        for key, value in config.items(section):
            if not hasattr(dialog, key):
                continue
            widget = getattr(dialog, key)
            # QTextEdit / QPlainTextEdit
            if hasattr(widget, 'setPlainText'):
                widget.setPlainText(value)
            elif hasattr(widget, 'setText'):
                widget.setText(value)
            elif hasattr(widget, 'setCurrentText'):
                widget.setCurrentText(value)
            elif hasattr(widget, 'setValue'):
                try:
                    widget.setValue(int(value))
                except ValueError:
                    try:
                        widget.setValue(float(value))
                    except ValueError:
                        pass
            elif hasattr(widget, 'setChecked'):
                widget.setChecked(value.lower() in ('1', 'true', 'yes', 'on'))


def main(config_file):
    apply_qgis_environment()
    qgis_app, _canvas, iface, _parent = get_qgis_app()
    if qgis_app is None:
        raise RuntimeError('QGIS could not be initialized')

    from ibtool import IBTool
    from ibtool_dialog import IBToolDialog

    plugin = IBTool(iface)
    plugin.dlg = IBToolDialog()
    plugin.setup_logging_in_plugin()

    cfg = configparser.ConfigParser()
    cfg.read(config_file)
    populate_dialog(plugin.dlg, cfg)

    add_stdout_logging()

    plugin.start_processing()

    qgis_app.exitQgis()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python3 scripts/run_cli.py /path/to/config.ini', file=sys.stderr)
        sys.exit(1)
    main(sys.argv[1])

