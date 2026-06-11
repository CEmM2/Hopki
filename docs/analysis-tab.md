# Analysis Tab

The Analysis tab is the main working area. It loads experiment data, runs the analysis every time a relevant control changes, and shows the intermediate and final plots.

## Experiment Controls

| Control | What it does |
| --- | --- |
| **Load experiment...** | Opens a folder picker. Choose the experiment directory containing signal files and configuration. |
| **Save config** | Writes a per-experiment `hopki.toml` containing only fields that differ from the inherited campaign/default configuration. This is useful after editing dimensions or accepting estimated distances. |
| **Revert config** | Reloads configuration from disk and discards live edits made in the GUI. |
| Directory label | Shows the currently loaded experiment path. |
| Editable fields | The text fields for bar, specimen, and damping values. Editing a field and leaving it reruns the analysis. See [Parameters](parameters.md) for every field. |
| Derived readout | Shows `tpp`, which is read from the signal time column, and warns when `x1` or `x2` was auto-estimated. |
| **Re-estimate x1, x2** | Recomputes both gauge distances from the loaded signals and replaces the current values. The status message reports `x1` correlation and `x2` signal-to-noise ratio. |
| **Pick x2 (2 clicks)** | Lets you set `x2` manually from the **Signals** plot. Click the incident pulse arrival, then the transmitted pulse arrival. Hopki computes `x2` from the time difference and the acquisition delay. |

## Parameter Controls

| Control | What it does |
| --- | --- |
| **Theme** | Switches the GUI between the available visual themes. |
| **invert signal polarity** | Negates both input channels before analysis. Use it when the incident pulse should be negative but appears positive. |
| **Poisson nu** | Poisson ratio used to build the Bancroft dispersion table. Range: `0.20` to `0.35`; default: `0.29`. |
| **reflect shift** | Integer sample shift applied to the reflected pulse after dispersion correction. Range: `-50` to `50`; default: `0`. Positive values delay the reflected pulse. |
| Slider below **reflect shift** | A faster way to adjust the same reflected-pulse shift. It stays synchronized with the numeric field. |
| `tim_cut` readout | Displays the pulse-start time set by the draggable marker on the **Signals** plot. |

## Graph Controls

The **Graphs** checklist toggles plot visibility. It does not change the analysis; it only hides or shows plots to make the tab easier to scan.

| Plot | What to inspect |
| --- | --- |
| **Signals** | Raw incident/reflected and transmitted voltage signals. Drag the vertical line here to set `tim_cut`. |
| **Windowed pulses** | The incident, reflected, and transmitted pulse windows cut from the raw signals. |
| **Corrected + aligned** | Pulses after dispersion/damping correction, with the reflected pulse shifted by **reflect shift**. |
| **Force equilibrium** | `f_in` and `f_out`. These should be compared when tuning alignment and checking whether the analysis window is reasonable. |
| **Force difference** | `f_in - f_out`. Drag the shaded region to report mean force difference over a selected time interval. |
| **Stress-strain** | Engineering and true stress-strain curves from the current analysis. |

## Bottom Buttons

| Button | What it does |
| --- | --- |
| **sigma-epsilon -> Figures** | Sends the current true stress-strain curve to the Figures tab. |
| **Export results...** | Opens an output-folder picker and writes MATLAB-style output files such as `inc_puls`, `ref_corr`, `f_in`, `s_e_eng`, and `s_e_true`. |

## Status Line

The status line reports the current striker velocity estimate and point count after a successful run. If a field is invalid or a pulse window is out of range, the same area shows the error.
