"""Publication-quality figure rendering via matplotlib (+ SciencePlots).

The Figures tab edits curves interactively with pyqtgraph (fast), but a screenshot of a
pyqtgraph plot is not journal-ready. For *export* we re-render the same :class:`~hopki.figio.
FigureDoc` with matplotlib: a SciencePlots style (https://github.com/garrettj403/SciencePlots),
configurable font sizes, optional LaTeX for the axis titles, and PNG/PDF output.

matplotlib reads styling from global rcParams, so a render runs inside a
``matplotlib.style.context([...tokens..., {rc overrides}])`` block (overrides last so font
sizes / usetex win over the chosen style). The object-oriented Agg path is used (no pyplot
global state / Qt backend), so this is safe to call from inside the Qt app and headlessly.
"""

from __future__ import annotations

import shutil
import warnings
from functools import lru_cache
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FormatStrFormatter

from .figio import FigureDoc

try:  # SciencePlots just registers extra styles on import; optional.
    import scienceplots  # noqa: F401  (import side-effect registers the styles)
    _HAVE_SCIENCEPLOTS = True
except ImportError:  # pragma: no cover - exercised only without the optional dep
    _HAVE_SCIENCEPLOTS = False

# matplotlib line-style / marker names for our figio enum values.
_MPL_LINE = {"solid": "-", "dash": "--", "dot": ":", "dashdot": "-.", "none": ""}
_MPL_MARKER = {"none": "", "o": "o", "s": "s", "t": "^", "d": "D", "+": "+", "x": "x"}

# SciencePlots presets (only offered when the package is importable), then matplotlib built-ins
# that ship with every install. "default" resets matplotlib to its stock look.
_SCIENCE_STYLES = ["science", "science,grid", "science,ieee", "science,nature", "science,scatter"]
_BUILTIN_STYLES = ["default", "seaborn-v0_8-paper", "ggplot", "bmh"]


def available_styles() -> list[str]:
    """Style names offered in the export dropdown (SciencePlots presets first, if installed)."""
    return (_SCIENCE_STYLES if _HAVE_SCIENCEPLOTS else []) + _BUILTIN_STYLES


@lru_cache(maxsize=1)
def latex_available() -> bool:
    """Whether matplotlib's ``text.usetex`` path can actually run on this machine.

    A TeX distribution cannot be bundled into a frozen binary (it is multi-GB and a system
    install), so a shipped Hopki may well run where there is no LaTeX. matplotlib's usetex
    pipeline shells out to ``latex`` and ``dvipng``; if either is missing it raises a cryptic
    error deep in a draw call. We probe for both up front so the GUI can disable the toggle and
    the renderer can fall back to mathtext instead of crashing. Cached — PATH won't change mid-run.
    """
    return shutil.which("latex") is not None and shutil.which("dvipng") is not None


def _effective_usetex(doc: FigureDoc) -> bool:
    """``doc.use_latex``, but downgraded to ``False`` (with a warning) when no TeX is installed,
    so export degrades to mathtext rather than failing."""
    if not doc.use_latex:
        return False
    if latex_available():
        return True
    warnings.warn(
        "LaTeX rendering requested but no TeX install was found (need 'latex' and 'dvipng' on "
        "PATH); falling back to mathtext for this figure.",
        RuntimeWarning,
        stacklevel=3,
    )
    return False


def _style_context(doc: FigureDoc):
    """A matplotlib style context for ``doc``: the chosen style tokens plus an rc-override dict
    (font sizes + usetex) applied last so they win over the style."""
    tokens: list = [t for t in doc.style.split(",") if t]  # "science,grid" -> ["science","grid"]
    tokens.append({
        # Pin the figure size so fonts (absolute points) stay proportioned — SciencePlots
        # otherwise forces a tiny 3.5x2.6in canvas, which makes large fonts overflow/clip.
        "figure.figsize": (doc.fig_width, doc.fig_height),
        "axes.labelsize": doc.label_fontsize,
        "axes.titlesize": doc.label_fontsize,
        "xtick.labelsize": doc.tick_fontsize,
        "ytick.labelsize": doc.tick_fontsize,
        "legend.fontsize": doc.legend_fontsize,
        "text.usetex": _effective_usetex(doc),
    })
    return matplotlib.style.context(tokens)


def render(doc: FigureDoc) -> Figure:
    """Render ``doc`` to a matplotlib :class:`~matplotlib.figure.Figure` (not shown/saved).

    Applies the document's style, font sizes, optional LaTeX, axis titles/limits, and per-curve
    style + trim + scale (via :meth:`FigureCurve.shown`). Caller owns the returned figure.
    """
    with _style_context(doc):
        fig = Figure(constrained_layout=True)
        FigureCanvasAgg(fig)  # attach an Agg canvas so savefig works without pyplot/Qt
        ax = fig.add_subplot(111)
        for c in doc.curves:
            x, y = c.shown()
            st = c.style
            ax.plot(
                x, y,
                color=st.color,
                linestyle=_MPL_LINE.get(st.line_style, "-"),
                linewidth=st.line_width,
                marker=_MPL_MARKER.get(st.symbol, ""),
                markersize=st.symbol_size,
                label=(c.name if st.show_in_legend else "_nolegend_"),
            )
        if doc.title:
            ax.set_title(doc.title)
        ax.set_xlabel(doc.x_label)
        ax.set_ylabel(doc.y_label)
        ax.xaxis.set_major_formatter(FormatStrFormatter(doc.x_format or "%g"))
        ax.yaxis.set_major_formatter(FormatStrFormatter(doc.y_format or "%g"))
        if doc.x_limits:
            ax.set_xlim(*doc.x_limits)
        if doc.y_limits:
            ax.set_ylim(*doc.y_limits)
        if any(c.style.show_in_legend for c in doc.curves):
            ax.legend()
        return fig


def export(doc: FigureDoc, path: str | Path, *, dpi: int = 300) -> Path:
    """Render ``doc`` and save it to ``path`` (PNG or PDF by extension) at ``dpi``.

    When ``doc.use_latex`` is set but no TeX is installed, rendering silently degrades to
    mathtext (see :func:`latex_available`/:func:`_effective_usetex`), so this never fails for a
    *missing* TeX. The ``RuntimeError`` net below only catches a TeX install that is present but
    *broken*, turning matplotlib's otherwise-cryptic failure into an actionable message.
    """
    out = Path(path)
    fig = render(doc)
    try:
        fig.savefig(out, dpi=dpi)
    except RuntimeError as exc:  # a present-but-broken latex/dvipng toolchain
        if _effective_usetex(doc):
            raise RuntimeError(
                "LaTeX rendering failed — 'latex'/'dvipng' are on PATH but the run errored. "
                f"Disable the LaTeX toggle to use mathtext instead. (matplotlib: {exc})"
            ) from exc
        raise
    return out
