# Curve Cleanup Tab

The Curve cleanup tab wraps Hopki's `figcorr` operations in an interactive UI. It is intended for stress-strain cleanup after analysis, but it can also load any compatible two-column curve file.

## Source

| Button | What it does |
| --- | --- |
| **Pull true sigma-epsilon** | Loads the current true stress-strain curve from the Analysis result. |
| **Pull engineering sigma-epsilon** | Loads the current engineering stress-strain curve from the Analysis result. |
| **Load curve file...** | Opens a two-column curve file from disk. |
| **-> True sigma-epsilon** | Converts the current engineering curve to true stress and true strain. Disabled when the current curve is already true stress-strain. |

## Trim / Crop

The vertical line on the plot is the cut/crop pointer.

| Button | What it does |
| --- | --- |
| **Zero** | Shifts the curve so the first point is at the origin. |
| **Cut < line** | Keeps points up to the vertical line and removes points after it. |
| **Crop line >** | Removes points before the vertical line and keeps the rest. |
| **Straighten (2 clicks)** | Click two points on the linear toe region. Hopki subtracts the fitted line offset to toe-straighten the curve. |
| **Slope (2 clicks)** | Click two points and Hopki reports the slope. The curve is not modified. |

## Transform

| Control | What it does |
| --- | --- |
| **Negate sigma** | Multiplies stress values by `-1`. |
| **Negate epsilon** | Multiplies strain values by `-1`. |
| Scale factor field | Numeric factor used by the scale buttons. A value of `0` is rejected. |
| **Scale sigma** | Multiplies stress by the scale factor. |
| **Scale epsilon** | Multiplies strain by the scale factor. |
| Shift amount field | Numeric constant used by the shift buttons. |
| **Shift sigma** | Adds the shift amount to stress. |
| **Shift epsilon** | Adds the shift amount to strain. |

## Filter

| Control | What it does |
| --- | --- |
| **Smooth...** | Opens a power-spectrum preview and overlays a filtered curve. |
| **cutoff** | Butterworth low-pass cutoff as normalized frequency. `1` means Nyquist; default is `0.20`; range is `0.01` to `0.99`. |
| Cutoff line | Draggable line in the spectrum plot. It stays synchronized with the cutoff field. |
| **Apply filter** | Commits the previewed smoothed curve. |
| **Cancel** | Leaves smoothing preview mode without changing the curve. |

## Output

| Button | What it does |
| --- | --- |
| **Back** | Undoes the last committed cleanup operation. |
| **-> Figures** | Sends the current cleaned curve to the Figures tab. |
| **Save...** | Saves the current curve. The default filename is based on the source, usually `<source>_corr`. |

## Status Messages

The status line tells you what operation was applied, reports slopes, and shows input errors such as invalid scale factors or failed file loads.
