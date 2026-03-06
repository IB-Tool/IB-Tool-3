# -*- coding: utf-8 -*-
"""
Scripts Package für IBTool Plugin

Dieses Paket enthält Utility-Skripte für das IBTool Plugin,
einschließlich der Kommandozeilen-Ausführung ohne GUI.
"""

import os
import sys

# Füge das Plugin-Verzeichnis zum Python-Pfad hinzu
_plugin_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

# Alle benötigten Pfade hinzufügen
_paths_to_add = [
    _plugin_dir,
    os.path.join(_plugin_dir, 'helpers'),
    os.path.join(_plugin_dir, 'ibtool_tools'),
    os.path.join(_plugin_dir, 'test')
]

for _path in _paths_to_add:
    if os.path.exists(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

def patch_all_imports():  # pylint: disable=too-many-locals,too-many-statements
    """Patche alle relativen Imports für CLI-Verwendung"""
    import importlib.util  # pylint: disable=import-outside-toplevel

    # Patche helpers.message zuerst (keine relativen Imports)
    message_path = os.path.join(_plugin_dir, 'helpers', 'message.py')
    if os.path.exists(message_path):
        spec = importlib.util.spec_from_file_location("message", message_path)
        message_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(message_module)
        sys.modules['message'] = message_module

    # Patche helpers.logger - ersetze relativen Import
    logger_path = os.path.join(_plugin_dir, 'helpers', 'logger.py')
    if os.path.exists(logger_path):
        with open(logger_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Ersetze relativen Import
        source = source.replace('from .message import msg', 'from message import msg')

        spec = importlib.util.spec_from_loader('logger', loader=None)
        logger_module = importlib.util.module_from_spec(spec)
        exec(source, logger_module.__dict__)  # nosec B102 pylint: disable=exec-used
        sys.modules['logger'] = logger_module

    # Patche alle anderen helpers-Module
    helpers_modules = [
        'geometry_utils', 'system_utils', 'data_loader'
    ]

    for module_name in helpers_modules:
        module_path = os.path.join(_plugin_dir, 'helpers', f'{module_name}.py')
        if os.path.exists(module_path):
            with open(module_path, 'r', encoding='utf-8') as f:
                source = f.read()

            # Ersetze relative Imports
            source = source.replace('from .message import msg', 'from message import msg')
            source = source.replace('from .logger import Logger', 'from logger import Logger')

            spec = importlib.util.spec_from_loader(module_name, loader=None)
            module = importlib.util.module_from_spec(spec)
            exec(source, module.__dict__)  # nosec B102 pylint: disable=exec-used
            sys.modules[module_name] = module

    # Patche ibtool_tools-Module
    ibtool_tools_dir = os.path.join(_plugin_dir, 'ibtool_tools')
    if os.path.exists(ibtool_tools_dir):
        for filename in os.listdir(ibtool_tools_dir):
            if filename.endswith('.py') and not filename.startswith('__'):
                module_name = filename[:-3]  # Entferne .py
                module_path = os.path.join(ibtool_tools_dir, filename)

                with open(module_path, 'r', encoding='utf-8') as f:
                    source = f.read()

                # Ersetze relative Imports
                source = source.replace('from ..helpers.', 'from ')
                source = source.replace('from .', 'from ')

                spec = importlib.util.spec_from_loader(module_name, loader=None)
                module = importlib.util.module_from_spec(spec)
                exec(source, module.__dict__)  # nosec B102 pylint: disable=exec-used
                sys.modules[module_name] = module

    # Patche ibtool_dialog aus ibtool/ Unterverzeichnis
    dialog_path = os.path.join(_plugin_dir, 'ibtool', 'ibtool_dialog.py')
    if os.path.exists(dialog_path):
        with open(dialog_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Ersetze relative Imports falls vorhanden
        source = source.replace('from .helpers.', 'from ')

        spec = importlib.util.spec_from_loader('ibtool_dialog', loader=None)
        dialog_module = importlib.util.module_from_spec(spec)
        exec(source, dialog_module.__dict__)  # nosec B102 pylint: disable=exec-used
        sys.modules['ibtool_dialog'] = dialog_module

    # Patche ibtool.py aus ibtool/ Unterverzeichnis
    ibtool_path = os.path.join(_plugin_dir, 'ibtool', 'ibtool.py')
    if os.path.exists(ibtool_path):
        with open(ibtool_path, 'r', encoding='utf-8') as f:
            source = f.read()

        # Ersetze alle relativen Imports
        source = source.replace('from .helpers.logger import Logger', 'from logger import Logger')
        source = source.replace('from .helpers.geometry_utils import', 'from geometry_utils import')
        source = source.replace('from .helpers.system_utils import', 'from system_utils import')
        source = source.replace('from .helpers.message import msg', 'from message import msg')
        source = source.replace('from .helpers.data_loader import *', 'from data_loader import *')
        source = source.replace('from .ibtool_tools.', 'from ')
        source = source.replace('from .ibtool_dialog import IBToolDialog', 'from ibtool_dialog import IBToolDialog')

        spec = importlib.util.spec_from_loader('ibtool', loader=None)
        ibtool_module = importlib.util.module_from_spec(spec)
        exec(source, ibtool_module.__dict__)  # nosec B102 pylint: disable=exec-used
        sys.modules['ibtool'] = ibtool_module

    return True

# Führe das Patching durch
patch_all_imports()

# Paket-Metadaten
__version__ = '1.0.0'
__author__ = 'Oliver Harig'
__email__ = 'ottmar.hittzfeld@web.de'
__description__ = 'IBTool Plugin Scripts Package'

# Verfügbare Module exportieren
__all__ = [
    'patch_all_imports',
]

# Cleanup der temporären Variablen
del _plugin_dir, _paths_to_add, _path
