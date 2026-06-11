# Command Line

Hopki also provides command-line tools. Use them when you need repeatable batch processing or want to run the same operation outside the GUI.

## `hopki-gui`

Launches the desktop app.

```bash
uv run hopki-gui
uv run hopki-gui path/to/experiment
```

If a directory is supplied, Hopki opens it as the initial experiment.

## `wft-to-csv`

Converts Nicolet `.WFT` oscilloscope captures into legacy `.FLT` text files.

```bash
uv run wft-to-csv input.WFT output.FLT
```

Use `--help` for batch options such as output directories.

## `twobar-analyze`

Runs the core analysis pipeline on an experiment directory and writes MATLAB-style output vectors.

```bash
uv run twobar-analyze EXP_DIR \
  --tim-cut 2.83e-5 \
  --reflect-shift 3 \
  --nu 0.29 \
  --invert \
  --out OUT_DIR
```

| Option | Meaning |
| --- | --- |
| `EXP_DIR` | Experiment directory. |
| `--tim-cut` | Required pulse-start time in seconds. |
| `--reflect-shift` | Reflected-pulse shift in samples. Default: `0`. |
| `--nu` | Poisson ratio for dispersion correction. Default: `0.29`. |
| `--invert` | Negates input signals before analysis. |
| `--out` | Output directory. Defaults to the experiment directory. |

## `figcorr`

Runs curve cleanup operations from the command line.

```bash
uv run figcorr CURVE --cut 256 --zero
```

Use `uv run figcorr --help` for the full operation list.
