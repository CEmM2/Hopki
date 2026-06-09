#!/usr/bin/env python3
"""Build the Hopki desktop GUI into a native binary with Nuitka — macOS, Windows, or Linux.

One entry point for every platform so CI can call the same command on each runner:

    uv sync --extra gui --extra packaging
    uv run python packaging/build.py

Output:
  * macOS   -> build/Hopki.app            (double-clickable bundle; zip/DMG to distribute)
  * Windows -> build/hopki_app.dist/      (contains Hopki.exe; zip the folder)
  * Linux   -> build/hopki_app.dist/      (contains Hopki; tar.gz the folder)

The flags mirror the original packaging/build_macos.sh. Notes that bite if changed:
  * Nuitka bundles *code*, not arbitrary data files: theme_seuss.css and the runtime window
    icon are included explicitly, or the app silently falls back to default theme colors.
  * QtOpenGL is imported dynamically by pyqtgraph, so static analysis misses it — force it in.
  * Icons are consumed from committed assets (hopki/gui/Hopki.{icns,ico}, Hopki_256.png) so CI
    needs no macOS-only sips/iconutil. Missing icons are regenerated locally when possible.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENTRY = "packaging/hopki_app.py"

# Flags shared across all platforms (1:1 with the proven build_macos.sh set).
COMMON = [
    "--standalone",
    "--enable-plugin=pyside6",
    "--include-module=PySide6.QtOpenGL",
    "--include-module=PySide6.QtOpenGLWidgets",
    "--include-data-files=hopki/gui/theme_seuss.css=theme_seuss.css",
    "--include-data-files=hopki/gui/Hopki_256.png=Hopki_256.png",
    "--include-data-files=hopki/gui/Hopki_banner.png=Hopki_banner.png",
    "--include-package-data=scienceplots",
    "--include-package-data=matplotlib",
    "--nofollow-import-to=pandas",
    "--nofollow-import-to=plotly",
    "--nofollow-import-to=seaborn",
    "--nofollow-import-to=tkinter",
    "--nofollow-import-to=pytest",
    "--nofollow-import-to=IPython",
    "--output-dir=build",
    "--output-filename=Hopki",
    "--assume-yes-for-downloads",
]


def _ensure_icon() -> None:
    """Make sure the platform's icon asset exists, regenerating it locally if it doesn't.

    In CI the icons are committed, so these are no-ops. The fallbacks only help local builds.
    """
    if sys.platform == "darwin" and not (ROOT / "hopki/gui/Hopki.icns").exists():
        subprocess.run(["bash", "packaging/make_icons.sh"], cwd=ROOT, check=True)
    if sys.platform.startswith("win") and not (ROOT / "hopki/gui/Hopki.ico").exists():
        subprocess.run([sys.executable, "packaging/make_ico.py"], cwd=ROOT, check=True)


def _platform_flags() -> list[str]:
    if sys.platform == "darwin":
        return [
            "--macos-create-app-bundle",
            "--macos-app-name=Hopki",
            "--macos-app-icon=hopki/gui/Hopki.icns",
        ]
    if sys.platform.startswith("win"):
        return [
            "--windows-icon-from-ico=hopki/gui/Hopki.ico",
            "--windows-console-mode=disable",
        ]
    return ["--linux-icon=hopki/gui/Hopki_256.png"]


def _finalize() -> Path:
    """Post-process Nuitka output and return the artifact path."""
    if sys.platform == "darwin":
        # Nuitka names the bundle after the entry script (hopki_app.app); use the product name.
        produced = ROOT / "build/hopki_app.app"
        artifact = ROOT / "build/Hopki.app"
        if artifact.exists():
            shutil.rmtree(artifact)
        produced.rename(artifact)
        return artifact
    return ROOT / "build/hopki_app.dist"


def main() -> int:
    _ensure_icon()
    cmd = [sys.executable, "-m", "nuitka", *COMMON, *_platform_flags(), ENTRY]
    print("=== nuitka ===\n" + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)

    artifact = _finalize()
    print("=== built ===")
    subprocess.run(["du", "-sh", str(artifact)], check=False)
    print(f"HOPKI_ARTIFACT={artifact}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
