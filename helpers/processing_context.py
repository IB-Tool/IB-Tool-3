# -*- coding: utf-8 -*-
"""Shared QGIS processing context for one pipeline section (e.g. one partition).

``processing.run()`` builds a new ``QgsProcessingContext`` for every call when
no context is passed (expression scopes, default encoding, settings — about
3 ms per call). With ~68,000 calls on the sample data this was ~24 % of the
total runtime. Inside ``shared_processing_context()`` all processing calls
that pass ``context=current_processing_context()`` reuse one context.

Usage::

    with shared_processing_context():
        result = processing.run("native:buffer", params,
                                context=current_processing_context())

Outside a ``with`` block ``current_processing_context()`` returns ``None`` and
``processing.run()`` behaves exactly as before (tools stay usable on their own
and in tests).

Design note — documented exception to "no global variables"
(``ai/core/constraints.md``): the active context is held in a
``contextvars.ContextVar``. It is scoped to the ``with`` block (always reset,
also on exceptions), carries no algorithm state, and only affects
performance, not results: the context is created with the same function
QGIS uses per call (``processing.tools.dataobjects.createContext``), and
output layers are still handed to the caller (``takeResultLayer``), so they
do not accumulate in the shared context.

Copyright: (C) 2026 by Oliver Harig
License: GNU General Public License v2 or later
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Optional

from qgis.core import QgsProcessingContext, QgsProcessingFeedback

_ACTIVE_CONTEXT: ContextVar[Optional[QgsProcessingContext]] = ContextVar(
    "ibtool_processing_context", default=None)


def current_processing_context() -> Optional[QgsProcessingContext]:
    """Return the shared processing context of the enclosing block, or ``None``.

    Pass the return value as ``context=`` to ``processing.run()``; ``None``
    makes ``processing.run()`` create its own context as usual.
    """
    return _ACTIVE_CONTEXT.get()


@contextmanager
def shared_processing_context() -> Iterator[QgsProcessingContext]:
    """Provide one fresh ``QgsProcessingContext`` for the enclosed processing calls.

    Use one block per partition: a fresh context per partition releases layers
    that QGIS loaded from string inputs into the context's temporary store.

    The context owns a ``QgsProcessingFeedback`` for its whole lifetime.
    Otherwise ``processing.run()`` would attach its short-lived per-call
    feedback object to the shared context (dangling pointer after the call).

    Yields:
        The shared ``QgsProcessingContext``.
    """
    # Imported lazily: the processing plugin is only importable once QGIS
    # (and its plugin path) is initialised.
    from processing.tools import dataobjects  # pylint: disable=import-outside-toplevel

    feedback = QgsProcessingFeedback()
    context = dataobjects.createContext(feedback)
    token = _ACTIVE_CONTEXT.set(context)
    try:
        yield context
    finally:
        _ACTIVE_CONTEXT.reset(token)
        context.setFeedback(None)
        del feedback
