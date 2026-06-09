#!/usr/bin/env bash
# Generate app icons from the master PNG (hopki/gui/Hopki.png, 2048x2048).
#
#   bash packaging/make_icons.sh
#
# Produces, in hopki/gui/:
#   Hopki.icns      multi-resolution macOS app-bundle icon (16..1024)
#   Hopki_256.png   lightweight window icon loaded at runtime (QIcon)
#
# Uses only macOS-native sips + iconutil (no ImageMagick needed).
set -euo pipefail

cd "$(dirname "$0")/.."
SRC="hopki/gui/Hopki.png"
[ -f "$SRC" ] || { echo "missing $SRC" >&2; exit 1; }

ICONSET="$(mktemp -d)/Hopki.iconset"
mkdir -p "$ICONSET"
for sz in 16 32 128 256 512; do
    sips -z $sz $sz "$SRC" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
    sips -z $((sz*2)) $((sz*2)) "$SRC" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o hopki/gui/Hopki.icns

# Lightweight runtime window icon (Qt loads this, not the 6.4 MB master).
sips -z 256 256 "$SRC" --out hopki/gui/Hopki_256.png >/dev/null

echo "=== generated ==="
ls -lh hopki/gui/Hopki.icns hopki/gui/Hopki_256.png
