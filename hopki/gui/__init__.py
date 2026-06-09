"""Hopki desktop GUI (PySide6 + pyqtgraph).

Kept deliberately thin: the analysis lives in ``hopki.twobar`` as pure functions, and
``hopki.gui.controller`` holds GUI state without importing Qt (so it is unit-testable
headlessly). ``hopki.gui.app`` is the only module that pulls in PySide6/pyqtgraph.
"""

from __future__ import annotations
