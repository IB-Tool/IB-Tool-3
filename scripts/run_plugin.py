import argparse
import configparser
import json
import logging
import os

from test.utilities import get_qgis_app
from ibtool import IBTool, logger


def load_config(path):
    if path.endswith('.json'):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    config = configparser.ConfigParser()
    config.read(path)
    data = {}
    for section in config.sections():
        data.update(dict(config.items(section)))
    return data


def main(config_path):
    params = load_config(config_path)

    qgis_app, canvas, iface, parent = get_qgis_app()
    if qgis_app is None:
        raise RuntimeError('QGIS environment not available')

    plugin = IBTool(iface)
    plugin.setup_logging_in_plugin()

    mapping = {
        'hu': 'HuPath',
        'rn': 'RnPath',
        'part': 'PartPath',
        'aux': 'AuxPath',
        'output': 'OutputPath',
        'workspace': 'WorkspacePath',
        'filter': 'FilterPath',
        'logdir': 'LogDirPath',
        'minoverlapblocks': 'MinOverlapBlocksBox',
        'globalfootprintdensity': 'GlobalFootprintDensityBox',
        'minbdgcount': 'MinBdgCountBox',
        'maxholesize': 'MaxHoleSizeBox',
        'maxgapsize': 'MaxGapSizeBox',
        'minarea': 'MinAreaBox',
        'minpatchsize': 'MinPatchSizeBox',
        'partstart': 'partstartBox',
        'partend': 'partendBox',
        'partlist': 'partlistBox',
        'spatialreference': 'SpatialReferenceBox',
        'partlog': 'PartLogBox',
        'loglevel': 'LogLevelBox',
    }

    for key, widget_name in mapping.items():
        if key not in params:
            continue
        widget = getattr(plugin.dlg, widget_name, None)
        if widget is None:
            continue
        value = params[key]
        if isinstance(widget, type(plugin.dlg.PartLogBox)) and widget_name.endswith('Box') and hasattr(widget, 'setChecked'):
            widget.setChecked(str(value).lower() in ['1', 'true', 'yes'])
        elif hasattr(widget, 'setText'):
            widget.setText(str(value))
        elif hasattr(widget, 'setValue'):
            widget.setValue(int(value))

    # Stream handler for console logs
    stream_handler = logging.StreamHandler()
    logging.getLogger().addHandler(stream_handler)

    plugin.start_processing()
    qgis_app.exitQgis()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run IBTool without GUI')
    parser.add_argument('-c', '--config', default='config.ini', help='Path to config file (.ini or .json)')
    args = parser.parse_args()
    main(args.config)
