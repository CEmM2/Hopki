<p align="center">
  <img src="hopki/gui/Hopki_banner.png" alt="Hopki" width="640">
</p>

# Hopki

Hopki is a desktop app and command-line toolkit for analyzing **split Hopkinson bar**
experiments (compression and tension) — turning raw oscilloscope captures into
dispersion-corrected stress–strain curves and publication-ready figures.

It is a from-scratch Python reimplementation of a legacy MATLAB analysis suite, validated
to within 1e-8 of the original's reference outputs.

## Features

- **WFT → FLT conversion** of Nicolet oscilloscope binary captures (`wft-to-csv`).
- **Two-bar analysis pipeline**: pulse windowing, frequency-domain **dispersion correction**
  (Bancroft phase velocity), reflected-pulse alignment, and engineering/true stress–strain.
- **Interactive desktop GUI** (PySide6 + pyqtgraph): load an experiment, pick the pulse
  window and bar geometry by dragging, toggle polarity / Poisson ratio, and view every
  derived signal live.
- **Curve cleanup** (toe correction, smoothing, true-strain conversion) and a
  **publication-figure builder** (matplotlib / SciencePlots export to PNG/PDF).

## Download (prebuilt binaries)

Grab the latest build for your OS from the [Releases](https://github.com/CEmM2/Hopki/releases) page:

| OS | Asset | Run |
| --- | --- | --- |
| macOS | `Hopki-macos-*.zip` | unzip → open `Hopki.app` |
| Windows | `Hopki-windows-*.zip` | unzip → run `Hopki.exe` |
| Linux | `Hopki-linux-*.tar.gz` | extract → `./Hopki` |

The binaries are **unsigned**, so the OS may warn on first launch:

- **macOS** — right-click `Hopki.app` → **Open** (or `xattr -dr com.apple.quarantine Hopki.app`).
- **Windows** — SmartScreen → **More info** → **Run anyway**.

## Run from source

Hopki uses [uv](https://docs.astral.sh/uv/) and Python 3.12.

```bash
uv sync --extra gui          # GUI + analysis; omit --extra gui for a CLI-only install
uv run hopki-gui             # launch the desktop app
```

Command-line entry points (add `--help` to any for the full option list):

```bash
uv run wft-to-csv input.WFT out.FLT            # Nicolet .WFT -> legacy .FLT export
uv run twobar-analyze EXP_DIR --out OUTDIR     # run the analysis pipeline on an experiment dir
uv run figcorr CURVE --cut 256 --zero          # curve cleanup (toe correction, smoothing, …)
```

## Documentation

The user guide is now an MkDocs site under [`docs/`](docs/). Build or preview it with:

```bash
uv sync --extra docs
uv run mkdocs serve
```

A PDF copy is available at [`docs/Hopki_User_Guide.pdf`](docs/Hopki_User_Guide.pdf).

## Test data

The fixtures under `tests/` include representative recorded signals from real split Hopkinson
bar experiments, released here for regression testing. Tests use the stdlib `unittest` runner;
address modules by their dotted path (GUI tests run headless):

```bash
uv run python -m unittest tests.analysis.test_twobar tests.Converter.test_wft_to_csv
QT_QPA_PLATFORM=offscreen uv run python -m unittest tests.gui.test_controller
```

## Building binaries

Binaries are produced with [Nuitka](https://nuitka.net/) via a single cross-platform script
(the [release workflow](.github/workflows/release.yml) runs it on a macOS/Windows/Linux matrix
for each tagged version):

```bash
uv sync --extra gui --extra packaging
uv run python packaging/build.py
```

## License

MIT — see [LICENSE](LICENSE).
