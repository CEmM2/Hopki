"""Figures tab — assemble publication figures from one or more curves.

Load curves one at a time (2-column files, same as elsewhere) or many at once (a saved
``.npz`` figure); both accumulate. Per curve: legend label, colour, line/symbol type+size, and
a shown-x trim. Per figure: axis titles, tick number-format, and limits. Outputs: **Save** a
``.npz`` (curves + metadata, reloadable) and **Export** a PNG (alongside its ``.npz`` data).
"""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from typing import Callable

from hopki import figcorr, figio, figmpl
from hopki.figio import LINE_STYLES, PALETTE, SYMBOLS, CurveStyle, FigureCurve, FigureDoc

from .theme import Theme

CleanupSink = Callable[[object, object, str], None]  # (x, y, label) — matches app._send_to_cleanup

_QT_LINE = {
    "solid": QtCore.Qt.SolidLine, "dash": QtCore.Qt.DashLine,
    "dot": QtCore.Qt.DotLine, "dashdot": QtCore.Qt.DashDotLine,
}


def _parse_scale(text: str, fallback: float) -> float:
    """Parse a scale constant; keep ``fallback`` on a blank/invalid/zero value (0 collapses the
    curve and breaks the trim<->display conversion)."""
    try:
        value = float(text)
    except ValueError:
        return fallback
    return value if value != 0.0 else fallback


class _FmtAxis(pg.AxisItem):
    """An axis whose tick labels are formatted with a printf-style format string."""

    fmt = "%g"

    def tickStrings(self, values, scale, spacing):  # noqa: D102 (pyqtgraph hook)
        out = []
        for v in values:
            try:
                out.append(self.fmt % v)
            except (TypeError, ValueError):
                out.append(str(v))
        return out


class FiguresPanel(QtWidgets.QWidget):
    def __init__(self, send_to_cleanup: CleanupSink | None = None) -> None:
        super().__init__()
        self.doc = FigureDoc()
        self._send_to_cleanup = send_to_cleanup
        self._selected: int | None = None
        self._items: list[pg.PlotDataItem] = []
        self._theme: Theme | None = None
        self._syncing = False

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self._build_side())
        splitter.addWidget(self._build_plot())
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([330, 900])
        QtWidgets.QVBoxLayout(self).addWidget(splitter)
        self._refresh_list()
        self._set_style_enabled(False)

    # --------------------------------------------------------------- side panel
    def _build_side(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)

        # load / save / export
        btns = QtWidgets.QGridLayout()
        self.add_btn = QtWidgets.QPushButton("Add curve(s)…")
        self.add_btn.setToolTip("Load one or more 2-column curve files (multi-select); all append")
        self.add_btn.clicked.connect(self._on_add_curve)
        self.loadfig_btn = QtWidgets.QPushButton("Load figure…")
        self.loadfig_btn.clicked.connect(self._on_load_figure)
        self.save_btn = QtWidgets.QPushButton("Save (.npz)…")
        self.save_btn.clicked.connect(self._on_save)
        self.export_btn = QtWidgets.QPushButton("Export PNG/PDF…")
        self.export_btn.clicked.connect(self._on_export)
        for i, w in enumerate((self.add_btn, self.loadfig_btn, self.save_btn, self.export_btn)):
            btns.addWidget(w, i // 2, i % 2)
        layout.addLayout(btns)

        # curve list + delete / send-to-cleanup
        self.curve_list = QtWidgets.QListWidget()
        self.curve_list.currentRowChanged.connect(self._on_select)
        layout.addWidget(self.curve_list)
        row = QtWidgets.QHBoxLayout()
        self.delete_btn = QtWidgets.QPushButton("Delete curve")
        self.delete_btn.clicked.connect(self._on_delete)
        self.to_cleanup_btn = QtWidgets.QPushButton("→ Cleanup")
        self.to_cleanup_btn.setToolTip("Send the selected curve (as shown) to the Curve cleanup tab")
        self.to_cleanup_btn.clicked.connect(self.send_selected_to_cleanup)
        row.addWidget(self.delete_btn)
        row.addWidget(self.to_cleanup_btn)
        layout.addLayout(row)

        layout.addWidget(self._build_style_box())
        layout.addWidget(self._build_axes_box())
        layout.addWidget(self._build_export_box())
        layout.addStretch(1)
        scroll.setWidget(inner)
        return scroll

    def _build_style_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Selected curve")
        form = QtWidgets.QFormLayout(box)
        self.name_edit = QtWidgets.QLineEdit()
        self.name_edit.editingFinished.connect(self._apply_style)
        form.addRow("legend label", self.name_edit)
        self.color_btn = QtWidgets.QPushButton("colour")
        self.color_btn.clicked.connect(self._pick_color)
        form.addRow("colour", self.color_btn)
        self.line_combo = QtWidgets.QComboBox()
        self.line_combo.addItems(LINE_STYLES)
        self.line_combo.currentTextChanged.connect(self._apply_style)
        form.addRow("line", self.line_combo)
        self.width_spin = QtWidgets.QDoubleSpinBox()
        self.width_spin.setRange(0.5, 12.0)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.valueChanged.connect(self._apply_style)
        form.addRow("line width", self.width_spin)
        self.symbol_combo = QtWidgets.QComboBox()
        self.symbol_combo.addItems(SYMBOLS)
        self.symbol_combo.currentTextChanged.connect(self._apply_style)
        form.addRow("symbol", self.symbol_combo)
        self.symsize_spin = QtWidgets.QDoubleSpinBox()
        self.symsize_spin.setRange(2.0, 30.0)
        self.symsize_spin.valueChanged.connect(self._apply_style)
        form.addRow("symbol size", self.symsize_spin)
        self.xscale_edit = QtWidgets.QLineEdit("1")
        self.xscale_edit.setToolTip("Multiply x by this constant when drawing (e.g. 1e-6, 100)")
        self.xscale_edit.editingFinished.connect(self._apply_style)
        form.addRow("x scale", self.xscale_edit)
        self.yscale_edit = QtWidgets.QLineEdit("1")
        self.yscale_edit.setToolTip("Multiply y by this constant when drawing (e.g. 1e-6, 100)")
        self.yscale_edit.editingFinished.connect(self._apply_style)
        form.addRow("y scale", self.yscale_edit)
        self.legend_chk = QtWidgets.QCheckBox("show in legend")
        self.legend_chk.toggled.connect(self._apply_style)
        form.addRow(self.legend_chk)
        return box

    def _build_axes_box(self) -> QtWidgets.QGroupBox:
        box = QtWidgets.QGroupBox("Axes")
        form = QtWidgets.QFormLayout(box)
        self.xlabel_edit = QtWidgets.QLineEdit(self.doc.x_label)
        self.ylabel_edit = QtWidgets.QLineEdit(self.doc.y_label)
        self.xfmt_edit = QtWidgets.QLineEdit(self.doc.x_format)
        self.yfmt_edit = QtWidgets.QLineEdit(self.doc.y_format)
        for w in (self.xlabel_edit, self.ylabel_edit, self.xfmt_edit, self.yfmt_edit):
            w.editingFinished.connect(self._apply_axes_edits)
        form.addRow("x title", self.xlabel_edit)
        form.addRow("y title", self.ylabel_edit)
        form.addRow("x format", self.xfmt_edit)
        form.addRow("y format", self.yfmt_edit)

        self.xauto_chk = QtWidgets.QCheckBox("auto x limits")
        self.xauto_chk.setChecked(True)
        self.xauto_chk.toggled.connect(self._apply_axes_edits)
        self.xmin_edit = QtWidgets.QLineEdit()
        self.xmax_edit = QtWidgets.QLineEdit()
        self.yauto_chk = QtWidgets.QCheckBox("auto y limits")
        self.yauto_chk.setChecked(True)
        self.yauto_chk.toggled.connect(self._apply_axes_edits)
        self.ymin_edit = QtWidgets.QLineEdit()
        self.ymax_edit = QtWidgets.QLineEdit()
        for w in (self.xmin_edit, self.xmax_edit, self.ymin_edit, self.ymax_edit):
            w.editingFinished.connect(self._apply_axes_edits)
        form.addRow(self.xauto_chk)
        form.addRow("x min / max", self._pair(self.xmin_edit, self.xmax_edit))
        form.addRow(self.yauto_chk)
        form.addRow("y min / max", self._pair(self.ymin_edit, self.ymax_edit))
        return box

    def _build_export_box(self) -> QtWidgets.QGroupBox:
        """Publication-export settings: SciencePlots style, LaTeX, and font sizes (matplotlib).

        These affect the exported PNG/PDF only — the live pyqtgraph preview is unchanged.
        """
        box = QtWidgets.QGroupBox("Publication export")
        form = QtWidgets.QFormLayout(box)
        self.style_combo = QtWidgets.QComboBox()
        self.style_combo.addItems(figmpl.available_styles())
        self.style_combo.setCurrentText(self.doc.style)
        self.style_combo.currentTextChanged.connect(self._apply_export_edits)
        form.addRow("style", self.style_combo)
        self.latex_chk = QtWidgets.QCheckBox("LaTeX titles (needs a TeX install)")
        self.latex_chk.setChecked(self.doc.use_latex)
        self.latex_chk.toggled.connect(self._apply_export_edits)
        if not figmpl.latex_available():
            # No 'latex'/'dvipng' on PATH (e.g. a frozen binary on a machine without TeX):
            # disable the toggle so the user isn't offered an option that silently falls back.
            self.latex_chk.setEnabled(False)
            self.latex_chk.setText("LaTeX titles (no TeX install found — uses mathtext)")
            self.latex_chk.setToolTip(
                "Install a TeX distribution (with 'latex' and 'dvipng' on PATH) to enable "
                "LaTeX-rendered titles. Figures still export using matplotlib mathtext."
            )
        form.addRow(self.latex_chk)
        self.figw_spin = QtWidgets.QDoubleSpinBox()
        self.figw_spin.setRange(1.0, 20.0)
        self.figw_spin.setSingleStep(0.5)
        self.figw_spin.setValue(self.doc.fig_width)
        self.figw_spin.setToolTip("Export figure width in inches (overrides the style's size)")
        self.figw_spin.valueChanged.connect(self._apply_export_edits)
        self.figh_spin = QtWidgets.QDoubleSpinBox()
        self.figh_spin.setRange(1.0, 20.0)
        self.figh_spin.setSingleStep(0.5)
        self.figh_spin.setValue(self.doc.fig_height)
        self.figh_spin.setToolTip("Export figure height in inches")
        self.figh_spin.valueChanged.connect(self._apply_export_edits)
        form.addRow("size w × h [in]", self._pair(self.figw_spin, self.figh_spin))
        self.tickfs_spin = QtWidgets.QDoubleSpinBox()
        self.tickfs_spin.setRange(4.0, 40.0)
        self.tickfs_spin.setValue(self.doc.tick_fontsize)
        self.tickfs_spin.valueChanged.connect(self._apply_export_edits)
        form.addRow("tick font", self.tickfs_spin)
        self.labelfs_spin = QtWidgets.QDoubleSpinBox()
        self.labelfs_spin.setRange(4.0, 40.0)
        self.labelfs_spin.setValue(self.doc.label_fontsize)
        self.labelfs_spin.valueChanged.connect(self._apply_export_edits)
        form.addRow("axis-title font", self.labelfs_spin)
        self.legendfs_spin = QtWidgets.QDoubleSpinBox()
        self.legendfs_spin.setRange(4.0, 40.0)
        self.legendfs_spin.setValue(self.doc.legend_fontsize)
        self.legendfs_spin.valueChanged.connect(self._apply_export_edits)
        form.addRow("legend font", self.legendfs_spin)
        return box

    def _apply_export_edits(self, *_: object) -> None:
        if self._syncing:
            return
        self.doc.style = self.style_combo.currentText()
        self.doc.use_latex = self.latex_chk.isChecked()
        self.doc.fig_width = self.figw_spin.value()
        self.doc.fig_height = self.figh_spin.value()
        self.doc.tick_fontsize = self.tickfs_spin.value()
        self.doc.label_fontsize = self.labelfs_spin.value()
        self.doc.legend_fontsize = self.legendfs_spin.value()

    @staticmethod
    def _pair(a: QtWidgets.QWidget, b: QtWidgets.QWidget) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(a)
        lay.addWidget(b)
        return w

    def _build_plot(self) -> QtWidgets.QWidget:
        self._xaxis = _FmtAxis(orientation="bottom")
        self._yaxis = _FmtAxis(orientation="left")
        self.plot = pg.PlotWidget(axisItems={"bottom": self._xaxis, "left": self._yaxis})
        self._xaxis.enableAutoSIPrefix(False)
        self._yaxis.enableAutoSIPrefix(False)
        self.legend = self.plot.addLegend(offset=(10, 10))
        self.region = pg.LinearRegionItem()
        self.region.setZValue(-10)
        self.region.sigRegionChanged.connect(self._on_region)
        self.plot.addItem(self.region)
        self.region.hide()
        return self.plot

    # --------------------------------------------------------------- public API
    def add_curve(self, name: str, x: np.ndarray, y: np.ndarray) -> None:
        style = CurveStyle(color=PALETTE[len(self.doc.curves) % len(PALETTE)])
        self.doc.curves.append(FigureCurve(name=name, x=np.asarray(x, float),
                                           y=np.asarray(y, float), style=style))
        self._refresh_list()
        self.curve_list.setCurrentRow(len(self.doc.curves) - 1)
        self._render()

    def add_curve_from_file(self, path: str) -> None:
        from pathlib import Path
        curve = figcorr.load_curve(path)
        self.add_curve(Path(path).stem, curve.e, curve.s)

    def load_figure_file(self, path: str) -> None:
        doc = figio.load_figure(path)
        # accumulate: keep existing curves, append loaded ones; adopt axes if empty figure
        if not self.doc.curves:
            self.doc = doc
        else:
            self.doc.curves.extend(doc.curves)
        self._sync_axes_widgets()
        self._refresh_list()
        if self.doc.curves:
            self.curve_list.setCurrentRow(len(self.doc.curves) - 1)
        self._render()

    def save(self, path: str) -> None:
        figio.save_figure(self.doc, path)

    def export_png(self, path: str) -> None:
        """Render a publication-quality PNG/PDF via matplotlib (+ SciencePlots) and drop a
        ``.npz`` data sidecar next to it. (Name kept for back-compat; honours the extension.)"""
        from pathlib import Path

        figmpl.export(self.doc, path)
        figio.save_figure(self.doc, Path(path).with_suffix(".npz"))  # data alongside the image

    def send_selected_to_cleanup(self) -> None:
        """Hand the selected curve (as shown: trimmed + scaled) to the Curve cleanup tab."""
        if self._selected is None or self._send_to_cleanup is None:
            return
        c = self.doc.curves[self._selected]
        x, y = c.shown()
        self._send_to_cleanup(x, y, c.name)

    # ------------------------------------------------------------------ theming
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.plot.setBackground(theme.plot_bg)
        axis_pen = pg.mkPen(theme.plot_fg)
        for axis in (self._xaxis, self._yaxis):
            axis.setPen(axis_pen)
            axis.setTextPen(axis_pen)
        region_color = pg.mkColor(theme.accent)
        region_color.setAlpha(40)
        self.region.setBrush(region_color)
        self._apply_axes()

    # --------------------------------------------------------------- list/select
    def _refresh_list(self) -> None:
        self._syncing = True
        self.curve_list.clear()
        for c in self.doc.curves:
            self.curve_list.addItem(c.name)
        self._syncing = False

    def _on_select(self, row: int) -> None:
        self._selected = row if 0 <= row < len(self.doc.curves) else None
        if self._selected is None:
            self._set_style_enabled(False)
            self.region.hide()
            return
        self._set_style_enabled(True)
        self._populate_style(self.doc.curves[self._selected])

    def _populate_style(self, c: FigureCurve) -> None:
        self._syncing = True
        self.name_edit.setText(c.name)
        self._set_color_btn(c.style.color)
        self.line_combo.setCurrentText(c.style.line_style)
        self.width_spin.setValue(c.style.line_width)
        self.symbol_combo.setCurrentText(c.style.symbol)
        self.symsize_spin.setValue(c.style.symbol_size)
        self.xscale_edit.setText(f"{c.x_scale:g}")
        self.yscale_edit.setText(f"{c.y_scale:g}")
        self.legend_chk.setChecked(c.style.show_in_legend)
        self._sync_region(c)
        self._syncing = False

    def _sync_region(self, c: FigureCurve) -> None:
        """Place the trim region over the curve *as displayed* (raw x times x_scale).

        The trim is stored in raw x; here we convert to displayed coordinates so the draggable
        region tracks the scaled curve. Caller is responsible for the ``_syncing`` guard so the
        programmatic ``setRegion`` does not write back through ``_on_region``.
        """
        xs = c.x * c.x_scale
        if not xs.size:
            self.region.hide()
            return
        lo_raw = c.x_lo if c.x_lo is not None else float(c.x.min())
        hi_raw = c.x_hi if c.x_hi is not None else float(c.x.max())
        d_lo, d_hi = lo_raw * c.x_scale, hi_raw * c.x_scale
        self.region.setBounds((float(np.min(xs)), float(np.max(xs))))
        self.region.setRegion((min(d_lo, d_hi), max(d_lo, d_hi)))  # min/max: x_scale may be < 0
        self.region.show()

    # ----------------------------------------------------------------- edit ops
    def _apply_style(self, *_: object) -> None:
        if self._syncing or self._selected is None:
            return
        c = self.doc.curves[self._selected]
        c.name = self.name_edit.text() or c.name
        c.style.line_style = self.line_combo.currentText()
        c.style.line_width = self.width_spin.value()
        c.style.symbol = self.symbol_combo.currentText()
        c.style.symbol_size = self.symsize_spin.value()
        c.style.show_in_legend = self.legend_chk.isChecked()
        c.x_scale = _parse_scale(self.xscale_edit.text(), c.x_scale)
        c.y_scale = _parse_scale(self.yscale_edit.text(), c.y_scale)
        # Reflect a possibly-rejected scale back into the field, and move the trim region to
        # track the rescaled curve (guarded so the programmatic move isn't read back as an edit).
        self._syncing = True
        self.xscale_edit.setText(f"{c.x_scale:g}")
        self.yscale_edit.setText(f"{c.y_scale:g}")
        self._sync_region(c)
        self._syncing = False
        self.curve_list.item(self._selected).setText(c.name)
        self._render()

    def _pick_color(self) -> None:
        if self._selected is None:
            return
        c = self.doc.curves[self._selected]
        chosen = QtWidgets.QColorDialog.getColor(pg.mkColor(c.style.color), self, "Curve colour")
        if chosen.isValid():
            c.style.color = chosen.name()
            self._set_color_btn(c.style.color)
            self._render()

    def _on_region(self) -> None:
        if self._syncing or self._selected is None:
            return
        lo, hi = self.region.getRegion()  # displayed (scaled) coordinates
        c = self.doc.curves[self._selected]
        # Convert the trim back to raw x units (scale may be negative -> sort the bounds).
        scale = c.x_scale or 1.0
        r_lo, r_hi = lo / scale, hi / scale
        c.x_lo, c.x_hi = (min(r_lo, r_hi), max(r_lo, r_hi))
        # Drag fires continuously: update only the dragged curve's data, not the whole plot.
        if self._selected < len(self._items):
            x, y = c.shown()
            self._items[self._selected].setData(x, y)

    def _apply_axes_edits(self, *_: object) -> None:
        if self._syncing:
            return
        self.doc.x_label = self.xlabel_edit.text()
        self.doc.y_label = self.ylabel_edit.text()
        self.doc.x_format = self.xfmt_edit.text() or "%g"
        self.doc.y_format = self.yfmt_edit.text() or "%g"
        self.doc.x_limits = self._read_limits(self.xauto_chk, self.xmin_edit, self.xmax_edit)
        self.doc.y_limits = self._read_limits(self.yauto_chk, self.ymin_edit, self.ymax_edit)
        self._apply_axes()

    @staticmethod
    def _read_limits(auto: QtWidgets.QCheckBox, lo: QtWidgets.QLineEdit,
                     hi: QtWidgets.QLineEdit) -> tuple[float, float] | None:
        if auto.isChecked():
            return None
        try:
            vmin, vmax = float(lo.text()), float(hi.text())
        except ValueError:
            return None
        # Reject min >= max — pyqtgraph's tick generation chokes on an empty/inverted range.
        return (vmin, vmax) if vmin < vmax else None

    # ------------------------------------------------------------------ buttons
    def _on_add_curve(self) -> None:
        paths, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add curve(s) from file(s)")
        for path in paths:  # load each selected file; a bad one is reported but doesn't stop the rest
            self._guard("load curve", self.add_curve_from_file, path)

    def _on_load_figure(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Load figure", filter="Figures (*.npz)")
        if path:
            self._guard("load figure", self.load_figure_file, path)

    def _on_save(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save figure", "figure.npz")
        if path:
            self._guard("save figure", self.save, path)

    def _on_export(self) -> None:
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, "Export figure", "figure.png", filter="Images (*.png *.pdf)")
        if path:
            self._guard("export figure", self.export_png, path)

    def _guard(self, action: str, fn, path: str) -> None:
        """Run a file operation, surfacing any failure as a dialog instead of crashing."""
        try:
            fn(path)
        except Exception as exc:  # noqa: BLE001 — report any I/O/format failure to the user
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to {action}: {exc}")

    def _on_delete(self) -> None:
        if self._selected is None:
            return
        del self.doc.curves[self._selected]
        self._selected = None
        self._refresh_list()
        self._render()

    # -------------------------------------------------------------------- render
    def _render(self) -> None:
        for item in self._items:
            self.plot.removeItem(item)
        self._items = []
        self.legend.clear()
        for c in self.doc.curves:
            x, y = c.shown()
            pen = None if c.style.line_style == "none" else pg.mkPen(
                c.style.color, width=c.style.line_width, style=_QT_LINE[c.style.line_style])
            symbol = None if c.style.symbol == "none" else c.style.symbol
            item = pg.PlotDataItem(x, y, pen=pen, symbol=symbol,
                                   symbolSize=c.style.symbol_size,
                                   symbolBrush=c.style.color, symbolPen=c.style.color)
            self.plot.addItem(item)
            self._items.append(item)
            if c.style.show_in_legend:
                self.legend.addItem(item, c.name)
        self._apply_axes()

    def _apply_axes(self) -> None:
        color = self._theme.plot_fg if self._theme else "k"
        pi = self.plot.getPlotItem()
        pi.setTitle(self.doc.title or None, color=color, size="11pt")
        pi.getAxis("bottom").setLabel(self.doc.x_label, color=color)
        pi.getAxis("left").setLabel(self.doc.y_label, color=color)
        self._xaxis.fmt = self.doc.x_format
        self._yaxis.fmt = self.doc.y_format
        self._xaxis.update()
        self._yaxis.update()
        vb = pi.getViewBox()
        if self.doc.x_limits:
            vb.setXRange(*self.doc.x_limits, padding=0)
        else:
            vb.enableAutoRange(axis=vb.XAxis)
        if self.doc.y_limits:
            vb.setYRange(*self.doc.y_limits, padding=0)
        else:
            vb.enableAutoRange(axis=vb.YAxis)

    # -------------------------------------------------------------------- helpers
    def _sync_axes_widgets(self) -> None:
        self._syncing = True
        self.xlabel_edit.setText(self.doc.x_label)
        self.ylabel_edit.setText(self.doc.y_label)
        self.xfmt_edit.setText(self.doc.x_format)
        self.yfmt_edit.setText(self.doc.y_format)
        # adopt a loaded figure's publication-export settings too
        self.style_combo.setCurrentText(self.doc.style)
        self.latex_chk.setChecked(self.doc.use_latex)
        self.figw_spin.setValue(self.doc.fig_width)
        self.figh_spin.setValue(self.doc.fig_height)
        self.tickfs_spin.setValue(self.doc.tick_fontsize)
        self.labelfs_spin.setValue(self.doc.label_fontsize)
        self.legendfs_spin.setValue(self.doc.legend_fontsize)
        self._syncing = False

    def _set_color_btn(self, color: str) -> None:
        self.color_btn.setText(color)
        self.color_btn.setStyleSheet(f"background:{color}; color:white; font-weight:700;")

    def _set_style_enabled(self, enabled: bool) -> None:
        for w in (self.name_edit, self.color_btn, self.line_combo, self.width_spin,
                  self.symbol_combo, self.symsize_spin, self.xscale_edit, self.yscale_edit,
                  self.legend_chk, self.delete_btn, self.to_cleanup_btn):
            w.setEnabled(enabled)
        if not enabled:  # clear stale values from the previously selected curve
            self._syncing = True
            self.name_edit.clear()
            self.color_btn.setText("colour")
            self.color_btn.setStyleSheet("")
            self.line_combo.setCurrentIndex(0)
            self.symbol_combo.setCurrentIndex(0)
            self.xscale_edit.setText("1")
            self.yscale_edit.setText("1")
            self.legend_chk.setChecked(False)
            self._syncing = False
