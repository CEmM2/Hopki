#!/usr/bin/env bash
# Back-compat wrapper — the build is now cross-platform in packaging/build.py.
#
#   uv sync --extra gui --extra packaging
#   bash packaging/make_icons.sh        # once, to (re)generate Hopki.icns + Hopki_256.png
#   bash packaging/build_macos.sh       # -> build/Hopki.app  (delegates to build.py)
set -euo pipefail
cd "$(dirname "$0")/.."
exec uv run python packaging/build.py
