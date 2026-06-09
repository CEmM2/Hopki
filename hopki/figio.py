"""Figure document model + save/load for the publication-figures tab.

A :class:`FigureDoc` holds the figure-level settings (axis labels, tick formats, limits) and
a list of :class:`FigureCurve` (data + per-curve style + a shown-x-range trim). It is
persisted as a single ``.npz`` file: each curve's ``x``/``y`` are stored as arrays and all
metadata/styling as one JSON blob — self-contained, dependency-free, and reloadable (so a
saved figure can be reopened to add/remove/restyle curves).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

LINE_STYLES = ("solid", "dash", "dot", "dashdot", "none")
SYMBOLS = ("none", "o", "s", "t", "d", "+", "x")

# matplotlib tab10 — new curves cycle through these for distinct default colors.
PALETTE = [
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
    "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf",
]


@dataclass
class CurveStyle:
    color: str = "#1f77b4"
    line_style: str = "solid"      # one of LINE_STYLES
    line_width: float = 2.0
    symbol: str = "none"           # one of SYMBOLS
    symbol_size: float = 8.0
    show_in_legend: bool = True


@dataclass
class FigureCurve:
    name: str
    x: np.ndarray
    y: np.ndarray
    style: CurveStyle = field(default_factory=CurveStyle)
    x_lo: float | None = None      # shown-x trim window (in RAW x units); None = full extent
    x_hi: float | None = None
    x_scale: float = 1.0           # multiply x by this constant when drawing (unit conversion)
    y_scale: float = 1.0           # multiply y by this constant when drawing

    def shown(self) -> tuple[np.ndarray, np.ndarray]:
        """The (x, y) actually drawn: trim in raw x, then apply the per-axis scale constants.

        The trim window (``x_lo``/``x_hi``) is in raw x units so it selects the same data
        points regardless of ``x_scale``; scaling is a display transform applied afterwards.
        """
        lo = -np.inf if self.x_lo is None else self.x_lo
        hi = np.inf if self.x_hi is None else self.x_hi
        mask = (self.x >= lo) & (self.x <= hi)
        return self.x[mask] * self.x_scale, self.y[mask] * self.y_scale


@dataclass
class FigureDoc:
    curves: list[FigureCurve] = field(default_factory=list)
    x_label: str = "x"
    y_label: str = "y"
    x_format: str = "%g"
    y_format: str = "%g"
    title: str = ""
    x_limits: tuple[float, float] | None = None   # None = autoscale
    y_limits: tuple[float, float] | None = None
    # Publication export settings (matplotlib + SciencePlots — see hopki.figmpl).
    style: str = "default"          # a name from figmpl.available_styles()
    use_latex: bool = False         # render axis titles via LaTeX (needs a TeX install)
    # Figure size (inches) at export — overrides whatever the style picks, so fonts (in points)
    # stay correctly proportioned regardless of style (SciencePlots forces a tiny 3.5x2.6).
    fig_width: float = 6.4
    fig_height: float = 4.8
    tick_fontsize: float = 12.0
    label_fontsize: float = 14.0    # axis titles
    legend_fontsize: float = 12.0


def save_figure(doc: FigureDoc, path: str | Path) -> Path:
    """Write ``doc`` to a ``.npz`` (arrays + a JSON metadata blob)."""
    arrays: dict[str, np.ndarray] = {}
    meta: dict = {
        "x_label": doc.x_label, "y_label": doc.y_label,
        "x_format": doc.x_format, "y_format": doc.y_format, "title": doc.title,
        "x_limits": list(doc.x_limits) if doc.x_limits else None,
        "y_limits": list(doc.y_limits) if doc.y_limits else None,
        "style": doc.style, "use_latex": doc.use_latex,
        "fig_width": doc.fig_width, "fig_height": doc.fig_height,
        "tick_fontsize": doc.tick_fontsize, "label_fontsize": doc.label_fontsize,
        "legend_fontsize": doc.legend_fontsize,
        "curves": [],
    }
    for i, c in enumerate(doc.curves):
        arrays[f"c{i}_x"] = np.asarray(c.x, dtype=float)
        arrays[f"c{i}_y"] = np.asarray(c.y, dtype=float)
        meta["curves"].append({
            "name": c.name, "style": asdict(c.style), "x_lo": c.x_lo, "x_hi": c.x_hi,
            "x_scale": c.x_scale, "y_scale": c.y_scale,
        })
    arrays["meta"] = np.asarray(json.dumps(meta))

    out = Path(path)
    if out.suffix != ".npz":
        out = out.with_suffix(".npz")
    np.savez(out, **arrays)
    return out


def load_figure(path: str | Path) -> FigureDoc:
    """Read a ``.npz`` written by :func:`save_figure`."""
    with np.load(path, allow_pickle=False) as data:
        meta = json.loads(str(data["meta"].item()))
        curves = [
            FigureCurve(
                name=cm["name"], x=data[f"c{i}_x"], y=data[f"c{i}_y"],
                style=CurveStyle(**cm["style"]), x_lo=cm["x_lo"], x_hi=cm["x_hi"],
                x_scale=cm.get("x_scale", 1.0), y_scale=cm.get("y_scale", 1.0),
            )
            for i, cm in enumerate(meta["curves"])
        ]
    return FigureDoc(
        curves=curves, x_label=meta["x_label"], y_label=meta["y_label"],
        x_format=meta["x_format"], y_format=meta["y_format"], title=meta["title"],
        x_limits=tuple(meta["x_limits"]) if meta["x_limits"] else None,
        y_limits=tuple(meta["y_limits"]) if meta["y_limits"] else None,
        style=meta.get("style", "default"), use_latex=meta.get("use_latex", False),
        fig_width=meta.get("fig_width", 6.4), fig_height=meta.get("fig_height", 4.8),
        tick_fontsize=meta.get("tick_fontsize", 12.0),
        label_fontsize=meta.get("label_fontsize", 14.0),
        legend_fontsize=meta.get("legend_fontsize", 12.0),
    )
