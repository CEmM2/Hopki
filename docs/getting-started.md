# Getting Started

## Install Or Run

The easiest path is to download a prebuilt binary from the project releases page:

| OS | Release asset | First launch |
| --- | --- | --- |
| macOS | `Hopki-macos-*.zip` | Unzip, then right-click `Hopki.app` and choose **Open** if macOS warns about an unsigned app. |
| Windows | `Hopki-windows-*.zip` | Unzip and run `Hopki.exe`. If SmartScreen appears, choose **More info** then **Run anyway**. |
| Linux | `Hopki-linux-*.tar.gz` | Extract and run `./Hopki`. |

To run from source:

```bash
uv sync --extra gui
uv run hopki-gui
```

To open a specific experiment at launch:

```bash
uv run hopki-gui path/to/experiment
```

## Experiment Folder

Hopki expects an experiment directory with two signal channels and configuration.

Signal files are resolved in this order:

1. A local `hopki.toml` with a `[signals]` table.
2. `incid.inc` and `trans.tra`.
3. The first two `WAVE*.FLT` files by filename, incident first.

Configuration is resolved in layers:

1. Built-in defaults.
2. Any ancestor `hopki.toml` files, useful for campaign or bar constants.
3. The experiment's own `hopki.toml`.
4. Live edits made in the GUI.

If no `hopki.toml` exists in the experiment tree, Hopki falls back to the legacy files `incid.exp`, `incid.spec`, and `DAMP_F` when they are present.

## Minimal `hopki.toml`

```toml
[bar]
npoint = 450
diam_bar = 0.0127
E = 1.9e11
c0 = 4800
gfact = 2.13
vbridge = 10.15
damp_f = -0.018

[specimen]
diam = 0.004
length = 0.004
tdelay_us = 0
pretr_pct = 10

[signals]
incident = "WAVE0003.FLT"
transmitted = "WAVE0004.FLT"
```

`x1` and `x2` may be included in `[bar]`. If either is omitted, Hopki estimates it from the signals and marks the value for verification in the Analysis tab.

## First Analysis

1. Click **Load experiment...**.
2. Check that the **Signals** plot shows the incident/reflected channel and transmitted channel.
3. Drag the dashed vertical marker to the start of the incident pulse. This sets `tim_cut`.
4. If the pulse polarity is inverted, enable **invert signal polarity**.
5. Adjust **reflect shift** until the **Force equilibrium** and **Force difference** plots look reasonable.
6. Use **Export results...** to write output vectors, or **sigma-epsilon -> Figures** to start a publication plot.
