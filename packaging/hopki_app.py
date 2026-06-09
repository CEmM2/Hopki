"""Frozen-binary entry point for the Hopki desktop GUI.

The real GUI lives in ``hopki.gui.app:main`` and uses package-relative
imports, so a packager (Nuitka/PyInstaller) must compile *this* launcher and
follow imports into the ``hopki`` package, rather than compiling ``app.py``
directly.
"""

import sys

from hopki.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
