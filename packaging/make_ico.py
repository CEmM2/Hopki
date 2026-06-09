#!/usr/bin/env python3
"""Generate the Windows icon (hopki/gui/Hopki.ico) from the master PNG.

    uv run python packaging/make_ico.py

Pillow ships with matplotlib (a core dep), so this needs no extra install and — unlike the
macOS-only make_icons.sh (sips/iconutil) — runs on any platform. The resulting Hopki.ico is
committed so CI consumes it directly. The macOS .icns and the runtime Hopki_256.png are still
produced by make_icons.sh.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "hopki/gui/Hopki.png"
OUT = ROOT / "hopki/gui/Hopki.ico"
SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]


def main() -> int:
    if not SRC.exists():
        print(f"missing {SRC}", file=sys.stderr)
        return 1
    img = Image.open(SRC).convert("RGBA")
    img.save(OUT, format="ICO", sizes=SIZES)
    print(f"=== generated ===\n{OUT}  ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
