"""Curve-cleanup tab — an interactive front end for ``hopki.figcorr``.

Pulls the stress-strain curve from the analysis (or a file), then applies the figcorr
operations interactively: drag the pointer to cut/crop, set a cutoff to smooth, click two
points to toe-straighten or read a slope, undo with Back, and Save ``<name>_corr``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import re

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from hopki import figcorr
from hopki.figcorr import Curve

from .theme import Theme

LINE_WIDTH = 3
CurveSource = Callable[[str], "Curve | None"]
FiguresSink = Callable[[str, object, object], None]


def _sanitize_stem(label: str) -> str:
    """A filesystem-friendly file stem from a curve label (spaces/punctuation -> '_')."""
    stem = re.sub(r"[^0-9A-Za-z]+", "_", label).strip("_")
    return stem or "curve"


class CleanupPanel(QtWidgets.QWidget):
    """Interactive curve cleanup (figcorr) as a self-contained tab widget."""

    def __init__(self, get_analysis_curve: CurveSource,
                 send_to_figures: FiguresSink | None = None,
                 get_experiment_dir: "Callable[[], Path | None] | None" = None) -> None:
        super().__init__()
        self._get_analysis_curve = get_analysis_curve
        self._send_to_figures = send_to_figures
        self._get_experiment_dir = get_experiment_dir
        self._curve: Curve | None = None
        self._label = "cleaned curve"
        # Curve kind: "eng" / "true" / "file" / "explore". Only "true" disables the
        # engineering->true conversion (converting an already-true curve would be wrong).
        self._kind = "file"
        # Default Save location/name, set per source: the experiment folder (where the signals
        # and hopki.toml live) for analysis curves, or the loaded file's folder for file curves.
        self._save_dir: Path | None = None
        self._save_stem = "curve"
        self._history: list[tuple[Curve, str]] = []  # (curve, kind) snapshots for Back
        self._pick_mode: str | None = None
        self._pick_points: list[tuple[float, float]] = []
        self._smoothing = False  # True while previewing a frequency cutoff (not yet applied)
        self._syncing = False    # guards the cutoff line <-> spinbox round trip
        self._theme: Theme | None = None

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._build_side())
        splitter.addWidget(self._build_plot_area())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        QtWidgets.QVBoxLayout(self).addWidget(splitter)
        self._set_ops_enabled(False)

    # --------------------------------------------------------------- UI builders
    def _build_plot_area(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        v = QtWidgets.QVBoxLayout(w)
        self.plot = pg.PlotWidget()
        self.plot.addLegend(offset=(10, 10))
        self.curve_item = self.plot.plot([], [], name="curve")
        # Live filtered preview overlaid while choosing a cutoff (empty until smoothing).
        self.preview_curve = self.plot.plot([], [], name="filtered preview")
        self.pick_line = pg.InfiniteLine(angle=90, movable=True)
        self.plot.addItem(self.pick_line)
        self.plot.scene().sigMouseClicked.connect(self._on_plot_clicked)
        v.addWidget(self.plot, stretch=1)

        # Power-spectrum view with a draggable cutoff line — shown only during smooth preview.
        self.psd_plot = pg.PlotWidget()
        self.psd_plot.setMaximumHeight(190)
        self.psd_plot.setLogMode(y=True)  # spectra span decades; log makes the knee visible
        self.psd_curve = self.psd_plot.plot([], [], name="|FFT(σ)|")
        self.cutoff_line = pg.InfiniteLine(angle=90, movable=True, bounds=(0.01, 0.99))
        self.cutoff_line.sigPositionChanged.connect(self._on_cutoff_line_moved)
        self.psd_plot.addItem(self.cutoff_line)
        self.psd_plot.setVisible(False)
        v.addWidget(self.psd_plot)
        return w

    @staticmethod
    def _row(*widgets: QtWidgets.QWidget) -> QtWidgets.QWidget:
        """A flush horizontal row (e.g. a value field next to its two action buttons)."""
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            lay.addWidget(x)
        return w

    def _build_side(self) -> QtWidgets.QWidget:
        """Left sidebar of grouped operations (like the Figures tab), in a scroll area."""
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)

        # --- Source ---
        self.pull_true_btn = QtWidgets.QPushButton("Pull true σ–ε")
        self.pull_true_btn.clicked.connect(lambda: self._pull("true"))
        self.pull_eng_btn = QtWidgets.QPushButton("Pull engineering σ–ε")
        self.pull_eng_btn.clicked.connect(lambda: self._pull("eng"))
        self.load_btn = QtWidgets.QPushButton("Load curve file…")
        self.load_btn.clicked.connect(self._on_load)
        self.to_true_btn = QtWidgets.QPushButton("→ True σ–ε")
        self.to_true_btn.setToolTip(
            "Convert the current engineering σ–ε curve to true stress / true strain "
            "(eps_true = -ln(1-eps), σ_true = σ·(1+eps)). Disabled for a curve already "
            "pulled as true σ–ε. Use after trimming/scaling the engineering curve.")
        self.to_true_btn.clicked.connect(self._to_true)
        layout.addWidget(self._group("Source", self.pull_true_btn, self.pull_eng_btn,
                                     self.load_btn, self.to_true_btn))

        # --- Trim / crop ---
        self.zero_btn = QtWidgets.QPushButton("Zero")
        self.zero_btn.clicked.connect(self._zero)
        self.cut_btn = QtWidgets.QPushButton("Cut ◂ line")
        self.cut_btn.clicked.connect(self._cut)
        self.crop_btn = QtWidgets.QPushButton("Crop line ▸")
        self.crop_btn.clicked.connect(self._crop)
        self.straighten_btn = QtWidgets.QPushButton("Straighten (2 clicks)")
        self.straighten_btn.clicked.connect(lambda: self._begin_pick("straighten"))
        self.slope_btn = QtWidgets.QPushButton("Slope (2 clicks)")
        self.slope_btn.clicked.connect(lambda: self._begin_pick("slope"))
        layout.addWidget(self._group("Trim / crop", self.zero_btn, self.cut_btn, self.crop_btn,
                                     self.straighten_btn, self.slope_btn))

        # --- Transform (negate / scale / shift by a constant) ---
        self.neg_stress_btn = QtWidgets.QPushButton("Negate σ")
        self.neg_stress_btn.clicked.connect(lambda: self._negate("stress"))
        self.neg_strain_btn = QtWidgets.QPushButton("Negate ε")
        self.neg_strain_btn.clicked.connect(lambda: self._negate("strain"))
        self.factor_edit = QtWidgets.QLineEdit("1")
        self.factor_edit.setToolTip("Scale factor applied to the curve data (e.g. 1e-6, 100)")
        self.scale_stress_btn = QtWidgets.QPushButton("Scale σ")
        self.scale_stress_btn.clicked.connect(lambda: self._scale("stress"))
        self.scale_strain_btn = QtWidgets.QPushButton("Scale ε")
        self.scale_strain_btn.clicked.connect(lambda: self._scale("strain"))
        self.shift_edit = QtWidgets.QLineEdit("0")
        self.shift_edit.setToolTip("Constant added to one axis (σ = y, ε = x); e.g. -1e6, 0.05")
        self.shift_stress_btn = QtWidgets.QPushButton("Shift σ")
        self.shift_stress_btn.clicked.connect(lambda: self._shift("stress"))
        self.shift_strain_btn = QtWidgets.QPushButton("Shift ε")
        self.shift_strain_btn.clicked.connect(lambda: self._shift("strain"))
        layout.addWidget(self._group(
            "Transform",
            self._row(self.neg_stress_btn, self.neg_strain_btn),
            self._row(self.factor_edit, self.scale_stress_btn, self.scale_strain_btn),
            self._row(self.shift_edit, self.shift_stress_btn, self.shift_strain_btn)))

        # --- Filter (interactive low-pass) ---
        self.smooth_btn = QtWidgets.QPushButton("Smooth…")
        self.smooth_btn.setToolTip("Preview a low-pass cutoff on the power spectrum before applying")
        self.smooth_btn.clicked.connect(self._begin_smooth)
        self.cutoff_spin = QtWidgets.QDoubleSpinBox()
        self.cutoff_spin.setRange(0.01, 0.99)
        self.cutoff_spin.setSingleStep(0.02)
        self.cutoff_spin.setValue(0.20)
        self.cutoff_spin.setToolTip("Butterworth cutoff (normalized frequency; 1 = Nyquist)")
        self.cutoff_spin.valueChanged.connect(self._on_cutoff_spin_changed)
        self.apply_filter_btn = QtWidgets.QPushButton("Apply filter")
        self.apply_filter_btn.clicked.connect(self._apply_smooth)
        self.cancel_filter_btn = QtWidgets.QPushButton("Cancel")
        self.cancel_filter_btn.clicked.connect(self._cancel_smooth)
        for w in (self.apply_filter_btn, self.cancel_filter_btn):
            w.setVisible(False)
        filter_box = QtWidgets.QGroupBox("Filter")
        fform = QtWidgets.QFormLayout(filter_box)
        fform.addRow(self.smooth_btn)
        fform.addRow("cutoff", self.cutoff_spin)
        fform.addRow(self._row(self.apply_filter_btn, self.cancel_filter_btn))
        layout.addWidget(filter_box)

        # --- Output ---
        self.back_btn = QtWidgets.QPushButton("Back")
        self.back_btn.clicked.connect(self._back)
        self.figures_btn = QtWidgets.QPushButton("→ Figures")
        self.figures_btn.clicked.connect(self._send_figures)
        self.save_btn = QtWidgets.QPushButton("Save…")
        self.save_btn.clicked.connect(self._save)
        layout.addWidget(self._group("Output", self.back_btn, self.figures_btn, self.save_btn))

        self.status = QtWidgets.QLabel("Pull a curve from the analysis or load one to begin.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    @staticmethod
    def _group(title: str, *widgets: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox(title)
        v = QtWidgets.QVBoxLayout(box)
        for w in widgets:
            v.addWidget(w)
        return box

    # ------------------------------------------------------------------- theming
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.plot.setBackground(theme.plot_bg)
        pi = self.plot.getPlotItem()
        pi.setTitle("Stress–strain curve", color=theme.plot_fg, size="10pt")
        pi.showGrid(x=True, y=True, alpha=0.25)
        axis_pen = pg.mkPen(theme.plot_fg)
        for name, label in (("bottom", "strain"), ("left", "stress [Pa]")):
            ax = pi.getAxis(name)
            ax.setPen(axis_pen)
            ax.setTextPen(axis_pen)
            ax.setLabel(label, color=theme.plot_fg)
        self.curve_item.setPen(pg.mkPen(theme.engineering, width=LINE_WIDTH))
        self.preview_curve.setPen(pg.mkPen(theme.true_curve, width=LINE_WIDTH))
        self.pick_line.setPen(pg.mkPen(theme.orange, width=2, style=QtCore.Qt.DashLine))

        # Power-spectrum view (same palette as the main plot).
        self.psd_plot.setBackground(theme.plot_bg)
        ppi = self.psd_plot.getPlotItem()
        ppi.setTitle("σ power spectrum — drag to set the low-pass cutoff",
                     color=theme.plot_fg, size="10pt")
        ppi.showGrid(x=True, y=True, alpha=0.25)
        for name, label in (("bottom", "normalized frequency (1 = Nyquist)"), ("left", "|FFT(σ)|")):
            ax = ppi.getAxis(name)
            ax.setPen(axis_pen)
            ax.setTextPen(axis_pen)
            ax.setLabel(label, color=theme.plot_fg)
        self.psd_curve.setPen(pg.mkPen(theme.transmitted, width=2))
        self.cutoff_line.setPen(pg.mkPen(theme.orange, width=2, style=QtCore.Qt.DashLine))

    # ------------------------------------------------------------------- sources
    def _pull(self, kind: str) -> None:
        curve = self._get_analysis_curve(kind)
        if curve is None:
            self._set_status("No analysis result yet — load an experiment first.", error=True)
            return
        self._label = f"{kind} σ–ε"
        # Save next to the experiment (signals + hopki.toml); name like the analysis output.
        self._save_dir = self._experiment_dir()
        self._save_stem = "s_e_true" if kind == "true" else "s_e_eng"
        self._reset_with(curve, f"Pulled {kind} σ–ε from the analysis ({len(curve.e)} pts).",
                         kind=kind)

    def _send_figures(self) -> None:
        if self._curve is None or self._send_to_figures is None:
            return
        self._send_to_figures(self._label, self._curve.e, self._curve.s)

    def set_curve_data(self, e: np.ndarray, s: np.ndarray, label: str) -> None:
        """Load an arbitrary ``(x, y)`` curve (e.g. handed over from the Explore tab)."""
        curve = Curve(np.asarray(e, dtype=float).copy(), np.asarray(s, dtype=float).copy())
        self._label = label
        # Explore curves are analysis-derived too -> default to the experiment folder.
        self._save_dir = self._experiment_dir()
        self._save_stem = _sanitize_stem(label)
        self._reset_with(curve, f"Loaded “{label}” from Explore ({len(curve.e)} pts).",
                         kind="explore")

    def _on_load(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load curve file")
        if not path:
            return
        try:
            curve = figcorr.load_curve(path)
        except Exception as exc:
            self._set_status(f"load failed: {exc}", error=True)
            return
        self._label = Path(path).stem
        # File curves default back to the folder they came from.
        self._save_dir = Path(path).parent
        self._save_stem = Path(path).stem
        self._reset_with(curve, f"Loaded {path} ({len(curve.e)} pts).", kind="file")

    # ---------------------------------------------------------------- operations
    def _zero(self) -> None:
        self._apply(figcorr.zero(self._curve), "Zeroed to origin.")

    def _cut(self) -> None:
        idx = self._line_index()
        self._apply(figcorr.cut(self._curve, idx + 1), f"Cut to first {idx + 1} pts.")

    def _crop(self) -> None:
        idx = self._line_index()
        self._apply(figcorr.crop_start(self._curve, idx + 1), f"Cropped to start at pt {idx + 1}.")

    # ---------------------------------------------------- interactive smoothing
    def _begin_smooth(self) -> None:
        """Enter cutoff-preview mode: show the σ power spectrum with a draggable cutoff line
        and a live filtered overlay; nothing is committed until *Apply filter*."""
        if self._curve is None:
            return
        freq, mag = figcorr.power_spectrum(self._curve.s)
        if freq.size == 0:
            self._set_status("Curve too short to compute a spectrum.", error=True)
            return
        self.psd_curve.setData(freq, mag)
        self._set_smooth_mode(True)
        self.cutoff_line.setValue(float(self.cutoff_spin.value()))
        self._update_preview()
        self._set_status("Drag the line over the spectrum to set the cutoff, then Apply filter.")

    def _on_cutoff_line_moved(self) -> None:
        if not self._smoothing or self._syncing:
            return
        self._syncing = True
        self.cutoff_spin.setValue(float(self.cutoff_line.value()))
        self._syncing = False
        self._update_preview()

    def _on_cutoff_spin_changed(self, value: float) -> None:
        if not self._smoothing or self._syncing:
            return
        self._syncing = True
        self.cutoff_line.setValue(float(value))
        self._syncing = False
        self._update_preview()

    def _update_preview(self) -> None:
        """Recompute the filtered overlay for the current cutoff (no history change)."""
        if self._curve is None:
            return
        cutoff = float(self.cutoff_line.value())
        try:
            filtered = figcorr.smooth(self._curve, cutoff)
        except Exception as exc:  # e.g. degenerate cutoff for a very short curve
            self._set_status(f"preview failed: {exc}", error=True)
            return
        self.preview_curve.setData(filtered.e, filtered.s)
        self._set_status(f"cutoff {cutoff:.2f} (normalized; 1 = Nyquist) — Apply filter to keep.")

    def _apply_smooth(self) -> None:
        cutoff = float(self.cutoff_line.value())
        self._set_smooth_mode(False)
        self._apply(figcorr.smooth(self._curve, cutoff), f"Smoothed (cutoff {cutoff:.2f}).")

    def _cancel_smooth(self) -> None:
        self._set_smooth_mode(False)
        self._set_status("Filter cancelled.")

    def _set_smooth_mode(self, on: bool) -> None:
        self._smoothing = on
        self.psd_plot.setVisible(on)
        self.apply_filter_btn.setVisible(on)
        self.cancel_filter_btn.setVisible(on)
        if not on:
            self.preview_curve.setData([], [])
        # While previewing, disable the controls that would replace/redraw the curve out from
        # under the preview; the cutoff spinbox stays live as the numeric twin of the line.
        for w in (self.zero_btn, self.cut_btn, self.crop_btn, self.smooth_btn,
                  self.straighten_btn, self.slope_btn, self.neg_stress_btn,
                  self.neg_strain_btn, self.factor_edit, self.scale_stress_btn,
                  self.scale_strain_btn, self.shift_edit, self.shift_stress_btn,
                  self.shift_strain_btn, self.back_btn, self.figures_btn, self.save_btn,
                  self.pull_true_btn, self.pull_eng_btn, self.load_btn):
            w.setEnabled(not on)
        self._update_to_true_enabled()  # also gated on kind, so handle it separately

    def _negate(self, axis: str) -> None:
        label = "stress (σ)" if axis == "stress" else "strain (ε)"
        self._apply(figcorr.negate(self._curve, axis), f"Negated {label}.")

    def _scale(self, axis: str) -> None:
        try:
            factor = float(self.factor_edit.text())
        except ValueError:
            self._set_status("Scale factor must be a number.", error=True)
            return
        if factor == 0.0:
            self._set_status("Scale factor of 0 would collapse the curve — ignored.", error=True)
            return
        self._apply(figcorr.scale(self._curve, axis, factor), f"Scaled {axis} ×{factor:g}.")

    def _shift(self, axis: str) -> None:
        try:
            delta = float(self.shift_edit.text())
        except ValueError:
            self._set_status("Shift amount must be a number.", error=True)
            return
        self._apply(figcorr.shift(self._curve, axis, delta), f"Shifted {axis} by {delta:g}.")

    def _to_true(self) -> None:
        """Convert the current (engineering) curve to true σ–ε. Disabled for a true curve."""
        if self._curve is None or self._kind == "true":
            return
        self._apply(figcorr.to_true(self._curve),
                    "Converted to true stress / true strain.", new_kind="true")

    def _update_to_true_enabled(self) -> None:
        """The →True button is usable only for a non-true curve (and not mid smooth-preview)."""
        self.to_true_btn.setEnabled(
            self._curve is not None and self._kind != "true" and not self._smoothing)

    def _back(self) -> None:
        if not self._history:
            self._set_status("Nothing to undo.")
            return
        self._curve, self._kind = self._history.pop()
        self._redraw()
        self._update_to_true_enabled()
        self._set_status("Reverted last operation.")

    def _experiment_dir(self) -> "Path | None":
        """The current experiment directory (where signals + hopki.toml live), if available."""
        if self._get_experiment_dir is None:
            return None
        try:
            return self._get_experiment_dir()
        except Exception:
            return None

    def default_save_path(self) -> str:
        """Default Save target: ``<source folder>/<stem>_corr`` (the experiment folder for an
        analysis curve, the originating folder for a loaded file)."""
        name = f"{self._save_stem}_corr"
        return str(self._save_dir / name) if self._save_dir is not None else name

    def _save(self) -> None:
        if self._curve is None:
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Save curve", self.default_save_path())
        if not path:
            return
        try:
            figcorr.save_curve(self._curve, path)
        except Exception as exc:
            self._set_status(f"save failed: {exc}", error=True)
            return
        self._set_status(f"Saved {path}.")

    # --------------------------------------------------------------- 2-click ops
    def _begin_pick(self, mode: str) -> None:
        if self._curve is None:
            return
        self._pick_mode = mode
        self._pick_points = []
        verb = "two points on the linear region" if mode == "straighten" else "two points"
        self._set_status(f"{mode}: click {verb}…")

    def _on_plot_clicked(self, event: object) -> None:
        if self._pick_mode is None or self._curve is None:
            return
        vb = self.plot.getPlotItem().vb
        point = vb.mapSceneToView(event.scenePos())
        self._pick_points.append((float(point.x()), float(point.y())))
        if len(self._pick_points) < 2:
            self._set_status(f"{self._pick_mode}: one more click…")
            return
        p1, p2 = self._pick_points
        mode, self._pick_mode = self._pick_mode, None
        if mode == "slope":
            self._set_status(f"slope ≈ {figcorr.slope(p1, p2):.4g}")
        else:
            self._apply(figcorr.straighten(self._curve, p1, p2), "Toe-straightened.")

    # -------------------------------------------------------------------- helpers
    def _line_index(self) -> int:
        return int(np.argmin(np.abs(self._curve.e - float(self.pick_line.value()))))

    def _apply(self, new_curve: Curve, message: str, *, new_kind: str | None = None) -> None:
        if self._curve is None:
            return
        self._history.append((self._curve, self._kind))
        self._curve = new_curve
        if new_kind is not None:
            self._kind = new_kind
        self._redraw()
        self._update_to_true_enabled()
        self._set_status(message)

    def _reset_with(self, curve: Curve, message: str, kind: str) -> None:
        if self._smoothing:
            self._set_smooth_mode(False)
        self._curve = curve
        self._kind = kind
        self._history.clear()
        self._pick_mode = None
        self._redraw()
        self._set_ops_enabled(True)
        mid = float(np.median(curve.e))
        self.pick_line.setBounds((float(curve.e.min()), float(curve.e.max())))
        self.pick_line.setValue(mid)
        self._set_status(message)

    def _redraw(self) -> None:
        self.curve_item.setData(self._curve.e, self._curve.s)

    def _set_ops_enabled(self, enabled: bool) -> None:
        for w in (self.zero_btn, self.cut_btn, self.crop_btn, self.smooth_btn,
                  self.cutoff_spin, self.straighten_btn, self.slope_btn,
                  self.neg_stress_btn, self.neg_strain_btn,
                  self.factor_edit, self.scale_stress_btn, self.scale_strain_btn,
                  self.shift_edit, self.shift_stress_btn, self.shift_strain_btn,
                  self.back_btn, self.figures_btn, self.save_btn):
            w.setEnabled(enabled)
        self._update_to_true_enabled()  # gated on curve kind, not just the blanket flag

    def _set_status(self, text: str, *, error: bool = False) -> None:
        if self._theme is not None:
            color = self._theme.red if error else self._theme.text_muted
            self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)
