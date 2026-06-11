# Figures Tab

The Figures tab builds publication figures from one or more curves. It keeps figure data and styling together in a reloadable `.npz` file, and it exports PNG or PDF through matplotlib.

## File Buttons

| Button | What it does |
| --- | --- |
| **Add curve(s)...** | Loads one or more two-column curve files and appends them to the current figure. |
| **Load figure...** | Loads a saved `.npz` figure. If the current figure is empty, Hopki adopts its axes and settings; otherwise loaded curves are appended. |
| **Save (.npz)...** | Saves all curves plus figure metadata and styling to a reloadable `.npz`. |
| **Export PNG/PDF...** | Exports the figure as an image and writes a `.npz` sidecar next to it. |

## Curve List

| Control | What it does |
| --- | --- |
| Curve list | Selects which curve is edited by the **Selected curve** controls. |
| **Delete curve** | Removes the selected curve from the figure. |
| **-> Cleanup** | Sends the selected curve, as currently shown after trim and scaling, to the Curve cleanup tab. |

## Selected Curve

| Control | Meaning |
| --- | --- |
| **legend label** | Name shown in the figure legend and curve list. |
| **colour** | Opens a color picker. The button shows the selected color. |
| **line** | Line style: `solid`, `dash`, `dot`, `dashdot`, or `none`. |
| **line width** | Line width. Range: `0.5` to `12.0`; default is `2.0`. |
| **symbol** | Marker symbol: `none`, `o`, `s`, `t`, `d`, `+`, or `x`. |
| **symbol size** | Marker size. Range: `2.0` to `30.0`; default is `8.0`. |
| **x scale** | Multiplies x values when drawing. Use it for unit conversions, such as strain to percent. |
| **y scale** | Multiplies y values when drawing. Use it for unit conversions, such as Pa to MPa. |
| **show in legend** | Controls whether the selected curve appears in the legend. |

The shaded region on the plot trims the selected curve's displayed x range. The trim is stored in raw x units, so changing **x scale** does not change which data points are included.

## Axes

| Control | Meaning |
| --- | --- |
| **x title** | Horizontal axis title. |
| **y title** | Vertical axis title. |
| **x format** | printf-style numeric tick format for the x axis, for example `%g` or `%.2f`. |
| **y format** | printf-style numeric tick format for the y axis. |
| **auto x limits** | Lets Hopki autoscale the x axis. |
| **x min / max** | Manual x-axis limits when auto x limits is off. Invalid or inverted limits are ignored. |
| **auto y limits** | Lets Hopki autoscale the y axis. |
| **y min / max** | Manual y-axis limits when auto y limits is off. Invalid or inverted limits are ignored. |

## Publication Export

These settings affect exported PNG/PDF files. The live preview remains a pyqtgraph preview.

| Control | Meaning |
| --- | --- |
| **style** | Matplotlib/SciencePlots style used for export. |
| **LaTeX titles** | Uses LaTeX-rendered text when a TeX installation is available. If TeX is missing, the option is disabled and mathtext is used. |
| **size w x h [in]** | Export figure width and height in inches. Defaults: `6.4 x 4.8`. |
| **tick font** | Tick-label font size in points. Default: `12`. |
| **axis-title font** | Axis-title font size in points. Default: `14`. |
| **legend font** | Legend font size in points. Default: `12`. |
