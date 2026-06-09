"""Locate bundled data assets (the theme CSS, the window icon) from either a source checkout
or a frozen build.

Running from source, an asset sits next to this module in ``hopki/gui/``. In a Nuitka
``--macos-create-app-bundle`` (or PyInstaller) build the ``hopki`` package is compiled *into*
the executable, so the package directory no longer exists on disk and data files are instead
placed flat next to the launcher (``Contents/MacOS/``). :func:`asset_path` tries both so the
same ``Path(__file__).with_name(...)``-style call works in every layout.
"""

from __future__ import annotations

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """Path to bundled asset ``name``, checked against source- and frozen-build locations.

    Returns the first candidate that exists; if none do, returns the source-tree path so the
    caller's own missing-file handling (e.g. the theme loader's defaults) still applies.
    """
    candidates = [
        Path(__file__).with_name(name),                 # source checkout: hopki/gui/<name>
        Path(sys.argv[0]).resolve().parent / name,      # frozen: next to the launcher exe
        Path(getattr(sys, "executable", "") or sys.argv[0]).resolve().parent / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]
