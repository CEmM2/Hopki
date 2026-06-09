"""Hopki desktop GUI — interactive core (PySide6 + pyqtgraph).

Tabbed window over the analysis pipeline. The *Analysis* tab loads an experiment, lets you
drag a marker to set ``tim_cut``, edit the configuration in place, toggle which graphs are
shown, and tune polarity / ``nu`` / ``reflect_shift`` — every change re-runs the pure
pipeline and redraws. The *Curve cleanup* tab wraps ``hopki.figcorr``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

from hopki.figcorr import Curve
from hopki.twobar import ExpConfig, SpecConfig

from .cleanup import CleanupPanel
from .controller import Controller
from .explore import ExplorePanel
from .figures import FiguresPanel
from .resources import asset_path
from .theme import Theme, load_themes

pg.setConfigOptions(antialias=True)

LINE_WIDTH = 3

# Lightweight (256px) window/dock icon — the 2048px Hopki.png master is the icon source but
# too heavy to load at runtime; make_icons.sh derives this from it.
_ICON_PATH = asset_path("Hopki_256.png")
# Wide banner — used for the startup splash and the About dialog.
_BANNER_PATH = asset_path("Hopki_banner.png")


def app_icon() -> QtGui.QIcon:
    """The Hopki window icon, or an empty QIcon if the asset is missing."""
    return QtGui.QIcon(str(_ICON_PATH)) if _ICON_PATH.exists() else QtGui.QIcon()


def _app_version() -> str:
    """Installed package version, falling back to the pyproject value for source/frozen runs."""
    try:
        return version("hopki")
    except PackageNotFoundError:
        return "0.1.0"


class _WatermarkHost(QtWidgets.QWidget):
    """Wraps a content widget and floats a faint, centered logo over it as an empty-state hint.

    The watermark is click-through and is hidden once an experiment loads, so it never covers
    live plots. It recenters itself on resize.
    """

    def __init__(self, content: QtWidgets.QWidget, pixmap: QtGui.QPixmap) -> None:
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(content)
        self._mark = QtWidgets.QLabel(self)
        self._mark.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self._mark.setStyleSheet("background: transparent;")
        if not pixmap.isNull():
            self._mark.setPixmap(pixmap)
            self._mark.resize(pixmap.size())
        effect = QtWidgets.QGraphicsOpacityEffect(self._mark)
        effect.setOpacity(0.10)
        self._mark.setGraphicsEffect(effect)
        self._mark.raise_()

    def set_watermark_visible(self, on: bool) -> None:
        self._mark.setVisible(on)

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self._mark.move((self.width() - self._mark.width()) // 2,
                        (self.height() - self._mark.height()) // 2)


class AboutDialog(QtWidgets.QDialog):
    """Help ▸ About Hopki — branding, version, author, license, and a repo link."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("About Hopki")
        self.setMinimumWidth(460)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if _BANNER_PATH.exists():
            pm = QtGui.QPixmap(str(_BANNER_PATH))
            if not pm.isNull():
                banner = QtWidgets.QLabel()
                banner.setPixmap(pm.scaledToWidth(460, QtCore.Qt.SmoothTransformation))
                banner.setAlignment(QtCore.Qt.AlignCenter)
                layout.addWidget(banner)

        body = QtWidgets.QLabel(
            "<div style='padding:14px'>"
            f"<h2 style='margin:0 0 6px'>Hopki "
            f"<span style='font-weight:normal;font-size:13px'>v{_app_version()}</span></h2>"
            "<p style='margin:0 0 10px'>Split Hopkinson bar experiment analysis — desktop GUI "
            "+ CLI.<br>A from-scratch Python port of the legacy MATLAB "
            "<code>twobar_g</code> suite.</p>"
            "<p style='margin:0'>© 2026 Shmuel Osovski · MIT License<br>"
            "<a href='https://github.com/CEmM2/Hopki'>github.com/CEmM2/Hopki</a></p>"
            "</div>"
        )
        body.setOpenExternalLinks(True)
        body.setWordWrap(True)
        layout.addWidget(body)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

# Editable configuration fields: (key, label). npoint is integer; the rest are floats.
# tpp is not here — it is derived from the signal's time column and shown read-only below.
_CONFIG_FIELDS = [
    ("npoint", "npoint"), ("diam_bar", "Ø bar [m]"), ("E", "E [Pa]"),
    ("x1", "x1 [m]"), ("x2", "x2 [m]"), ("c0", "c0 [m/s]"), ("gfact", "gauge factor"),
    ("vbridge", "V bridge"), ("diam_spec", "Ø spec [m]"), ("long_spec", "L spec [m]"),
    ("tdelay_us", "t delay [µs]"), ("pretr_pct", "pre-trig [%]"), ("damp_f", "damp_f"),
]


@dataclass
class _Plot:
    key: str
    widget: pg.PlotWidget
    legend: object
    title: str
    xlabel: str
    ylabel: str
    suffix: str = ""  # dynamic title addition (e.g. the force-difference average)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, theme: str = "Dark") -> None:
        super().__init__()
        self.setWindowTitle("Hopki — split Hopkinson bar analysis")
        self.setWindowIcon(app_icon())
        self.controller = Controller()
        self.themes = load_themes()
        self.theme: Theme = self.themes.get(theme, next(iter(self.themes.values())))
        self._syncing = False
        self._plots: list[_Plot] = []
        self._plot_by_key: dict[str, pg.PlotWidget] = {}
        self._themed_curves: list[tuple[object, str]] = []

        plots_widget = self._build_plots()       # populates the plot registries first
        controls_widget = self._build_controls()  # ...so the graphs checklist can mirror them
        self._plots_host = _WatermarkHost(plots_widget, self._watermark_pixmap())

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(controls_widget)
        splitter.addWidget(self._plots_host)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([340, 900])

        self.figures_panel = FiguresPanel(send_to_cleanup=self._send_to_cleanup)
        self.explore_panel = ExplorePanel(self._mechanics, self._send_to_cleanup,
                                          self._send_to_figures)
        self.cleanup_panel = CleanupPanel(
            self._analysis_curve, self._send_to_figures,
            get_experiment_dir=lambda: self.controller.directory)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(splitter, "Analysis")
        self.tabs.addTab(self.explore_panel, "Explore")
        self.tabs.addTab(self.cleanup_panel, "Curve cleanup")
        self.tabs.addTab(self.figures_panel, "Figures")
        self.setCentralWidget(self.tabs)
        self.resize(1300, 880)

        self._build_menu()
        self.apply_theme(self.theme.name)
        self._set_enabled(False)

    def _watermark_pixmap(self) -> QtGui.QPixmap:
        """The faint empty-state logo (scaled from the 256px icon), or a null pixmap if absent."""
        if not _ICON_PATH.exists():
            return QtGui.QPixmap()
        return QtGui.QPixmap(str(_ICON_PATH)).scaledToWidth(240, QtCore.Qt.SmoothTransformation)

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("Help")
        about_act = QtGui.QAction("About Hopki", self)
        about_act.triggered.connect(self._show_about)
        help_menu.addAction(about_act)

    def _show_about(self) -> None:
        AboutDialog(self).exec()

    # ----------------------------------------------------------------- controls
    def _build_controls(self) -> QtWidgets.QWidget:
        panel = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(panel)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(inner)

        # --- Experiment (load + editable config) ---
        exp_box = QtWidgets.QGroupBox("Experiment")
        exp_layout = QtWidgets.QVBoxLayout(exp_box)
        load_row = QtWidgets.QHBoxLayout()
        self.load_btn = QtWidgets.QPushButton("Load experiment…")
        self.load_btn.clicked.connect(self._on_load_clicked)
        self.save_cfg_btn = QtWidgets.QPushButton("Save config")
        self.save_cfg_btn.setToolTip("Write a per-experiment hopki.toml of the changed fields")
        self.save_cfg_btn.clicked.connect(self._on_save_config)
        self.revert_btn = QtWidgets.QPushButton("Revert config")
        self.revert_btn.setToolTip("Re-read config from disk (hopki.toml / legacy files)")
        self.revert_btn.clicked.connect(self._on_revert_config)
        load_row.addWidget(self.load_btn)
        load_row.addWidget(self.save_cfg_btn)
        load_row.addWidget(self.revert_btn)
        exp_layout.addLayout(load_row)
        self.dir_label = QtWidgets.QLabel("<no experiment loaded>")
        self.dir_label.setWordWrap(True)
        exp_layout.addWidget(self.dir_label)
        self._cfg_fields: dict[str, QtWidgets.QLineEdit] = {}
        cfg_form = QtWidgets.QFormLayout()
        for key, label in _CONFIG_FIELDS:
            field = QtWidgets.QLineEdit()
            field.editingFinished.connect(self._apply_config_edits)
            self._cfg_fields[key] = field
            cfg_form.addRow(label, field)
        exp_layout.addLayout(cfg_form)
        # Read-only derived values: tpp (from the signal) and any auto-estimated distances.
        self.derived_readout = QtWidgets.QLabel()
        self.derived_readout.setWordWrap(True)
        exp_layout.addWidget(self.derived_readout)
        dist_row = QtWidgets.QHBoxLayout()
        self.reestimate_btn = QtWidgets.QPushButton("Re-estimate x1, x2")
        self.reestimate_btn.setToolTip(
            "Re-derive both gauge distances from the signals, overriding config "
            "(useful when the TOML's x1/x2 are stale from an older setup).")
        self.reestimate_btn.clicked.connect(self._on_reestimate_distances)
        self.pick_x2_btn = QtWidgets.QPushButton("Pick x2 (2 clicks)")
        self.pick_x2_btn.setCheckable(True)
        self.pick_x2_btn.setToolTip(
            "Click the incident pulse arrival then the transmitted pulse arrival on the "
            "Signals plot to set x2 by hand (more reliable than the auto-estimate).")
        self.pick_x2_btn.clicked.connect(self._on_pick_x2_toggled)
        dist_row.addWidget(self.reestimate_btn)
        dist_row.addWidget(self.pick_x2_btn)
        exp_layout.addLayout(dist_row)
        layout.addWidget(exp_box)

        # --- Analysis parameters ---
        par_box = QtWidgets.QGroupBox("Parameters")
        form = QtWidgets.QFormLayout(par_box)
        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(list(self.themes))
        self.theme_combo.setCurrentText(self.theme.name)
        self.theme_combo.currentTextChanged.connect(self.apply_theme)
        form.addRow("Theme", self.theme_combo)

        self.invert_chk = QtWidgets.QCheckBox("invert signal polarity")
        self.invert_chk.toggled.connect(self._on_invert)
        form.addRow(self.invert_chk)

        self.nu_spin = QtWidgets.QDoubleSpinBox()
        self.nu_spin.setRange(0.20, 0.35)
        self.nu_spin.setSingleStep(0.01)
        self.nu_spin.setValue(0.29)
        self.nu_spin.valueChanged.connect(self._on_nu)
        form.addRow("Poisson ν", self.nu_spin)

        self.shift_spin = QtWidgets.QSpinBox()
        self.shift_spin.setRange(-50, 50)
        self.shift_spin.valueChanged.connect(self._on_shift)
        self.shift_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.shift_slider.setRange(-50, 50)
        self.shift_slider.valueChanged.connect(self.shift_spin.setValue)
        self.shift_spin.valueChanged.connect(self.shift_slider.setValue)
        form.addRow("reflect shift", self.shift_spin)
        form.addRow(self.shift_slider)
        self.timcut_readout = QtWidgets.QLabel("tim_cut: —")
        form.addRow(self.timcut_readout)
        layout.addWidget(par_box)

        # --- Graphs checklist (toggle visibility instead of scrolling/collapsing) ---
        graphs_box = QtWidgets.QGroupBox("Graphs")
        graphs_layout = QtWidgets.QVBoxLayout(graphs_box)
        self.graphs_list = QtWidgets.QListWidget()
        for p in self._plots:
            item = QtWidgets.QListWidgetItem(p.key)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(QtCore.Qt.Checked)
            self.graphs_list.addItem(item)
        self.graphs_list.itemChanged.connect(self._on_graph_toggled)
        self.graphs_list.setMaximumHeight(150)
        graphs_layout.addWidget(self.graphs_list)
        layout.addWidget(graphs_box)

        layout.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll, stretch=1)

        self.send_fig_btn = QtWidgets.QPushButton("σ–ε → Figures")
        self.send_fig_btn.setToolTip("Send the true stress–strain curve to the Figures tab")
        self.send_fig_btn.clicked.connect(self._on_send_sigeps)
        outer.addWidget(self.send_fig_btn)
        self.export_btn = QtWidgets.QPushButton("Export results…")
        self.export_btn.clicked.connect(self._on_export_clicked)
        outer.addWidget(self.export_btn)
        self.status = QtWidgets.QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        return panel

    # -------------------------------------------------------------------- plots
    def _add_plot(self, key: str, title: str, xlabel: str, ylabel: str) -> pg.PlotWidget:
        pw = pg.PlotWidget()
        pw.setMinimumHeight(240)
        legend = pw.addLegend(offset=(10, 10))
        self._plots.append(_Plot(key, pw, legend, title, xlabel, ylabel))
        self._plot_by_key[key] = pw
        self._sections_layout.addWidget(pw)
        return pw

    def _curve(self, pw: pg.PlotWidget, role: str, name: str) -> object:
        curve = pw.plot([], [], name=name)
        self._themed_curves.append((curve, role))
        return curve

    def _build_plots(self) -> QtWidgets.QWidget:
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        container = QtWidgets.QWidget()
        self._sections_layout = QtWidgets.QVBoxLayout(container)
        self._sections_layout.setContentsMargins(6, 6, 6, 6)

        p = self._add_plot("Signals", "Signals — drag the line to set the pulse start (tim_cut)",
                            "time [s]", "amplitude [V]")
        self.c_inc = self._curve(p, "inc", "incident+reflected")
        self.c_tra = self._curve(p, "tra", "transmitted")
        self.timcut_line = pg.InfiniteLine(angle=90, movable=True)
        self.timcut_line.sigPositionChanged.connect(self._on_timcut_dragged)
        p.addItem(self.timcut_line)
        self._signals_plot = p
        # x2-by-clicks pick state (set up the scene handler once; gated by _x2_pick_pts)
        self._x2_pick_pts: list[float] | None = None
        self._x2_pick_lines: list[pg.InfiniteLine] = []
        p.scene().sigMouseClicked.connect(self._on_signals_clicked)

        p = self._add_plot("Windowed pulses", "Windowed pulses", "time [s]", "amplitude [V]")
        self.w_inc = self._curve(p, "inc", "incident")
        self.w_ref = self._curve(p, "ref", "reflected")
        self.w_tra = self._curve(p, "tra", "transmitted")

        p = self._add_plot("Corrected + aligned", "Dispersion-corrected + aligned",
                            "time [s]", "amplitude [V]")
        self.cc_inc = self._curve(p, "inc", "incident")
        self.cc_ref = self._curve(p, "ref", "reflected (shifted)")
        self.cc_tra = self._curve(p, "tra", "transmitted")

        p = self._add_plot("Force equilibrium", "Force equilibrium", "time [s]", "force [N]")
        self.f_in = self._curve(p, "inc", "f_in")
        self.f_out = self._curve(p, "ref", "f_out")

        p = self._add_plot("Force difference", "Force difference (f_in − f_out)",
                            "time [s]", "Δforce [N]")
        self.f_diff = self._curve(p, "eng", "f_in − f_out")
        self._fdiff_plot = self._plots[-1]
        self.fdiff_region = pg.LinearRegionItem()
        self.fdiff_region.setZValue(-10)
        self.fdiff_region.sigRegionChanged.connect(self._update_fdiff_avg)
        p.addItem(self.fdiff_region)
        self._fdiff_region_init = False

        p = self._add_plot("Stress–strain", "Stress–strain", "strain", "stress [Pa]")
        # Strain is O(0.1–1): show it literally (0.3), not pyqtgraph's milli-prefixed "300 ×1e-3".
        # The stress axis keeps auto SI prefixes (MPa/GPa are useful there).
        p.getPlotItem().getAxis("bottom").enableAutoSIPrefix(False)
        self.ss_eng = self._curve(p, "eng", "engineering")
        self.ss_true = self._curve(p, "true", "true")

        self._sections_layout.addStretch(1)
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------ theming
    def _role_color(self, role: str) -> str:
        return {
            "inc": self.theme.incident, "ref": self.theme.reflected,
            "tra": self.theme.transmitted, "eng": self.theme.engineering,
            "true": self.theme.true_curve,
        }[role]

    def apply_theme(self, name: str) -> None:
        self.theme = self.themes.get(name, self.theme)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.setStyleSheet(self.theme.qss())

        axis_pen = pg.mkPen(self.theme.plot_fg)
        for p in self._plots:
            p.widget.setBackground(self.theme.plot_bg)
            pi = p.widget.getPlotItem()
            pi.setTitle(p.title + p.suffix, color=self.theme.plot_fg, size="10pt")
            pi.showGrid(x=True, y=True, alpha=0.25)
            for axis_name, text in (("bottom", p.xlabel), ("left", p.ylabel)):
                axis = pi.getAxis(axis_name)
                axis.setPen(axis_pen)
                axis.setTextPen(axis_pen)
                axis.setLabel(text, color=self.theme.plot_fg)
            if p.legend is not None:
                p.legend.setLabelTextColor(self.theme.plot_fg)

        for curve, role in self._themed_curves:
            curve.setPen(pg.mkPen(self._role_color(role), width=LINE_WIDTH))
        self.timcut_line.setPen(pg.mkPen(self.theme.timcut, width=2, style=QtCore.Qt.DashLine))
        region_color = pg.mkColor(self.theme.accent)
        region_color.setAlpha(40)
        self.fdiff_region.setBrush(region_color)
        if hasattr(self, "explore_panel"):
            self.explore_panel.apply_theme(self.theme)
        if hasattr(self, "cleanup_panel"):
            self.cleanup_panel.apply_theme(self.theme)
        if hasattr(self, "figures_panel"):
            self.figures_panel.apply_theme(self.theme)

    def _mechanics(self) -> "object | None":
        """Provide the current Mechanics to the Explore tab (or None)."""
        r = self.controller.result
        return r.mechanics if r is not None else None

    def _send_to_cleanup(self, x: object, y: object, label: str) -> None:
        """Hand the Explore tab's current curve to Curve cleanup and switch to it."""
        self.cleanup_panel.set_curve_data(x, y, label)
        self.tabs.setCurrentWidget(self.cleanup_panel)

    def _send_to_figures(self, name: str, x: object, y: object) -> None:
        """Add a curve to the Figures tab and switch to it."""
        self.figures_panel.add_curve(name, x, y)
        self.tabs.setCurrentWidget(self.figures_panel)

    def _on_send_sigeps(self) -> None:
        r = self.controller.result
        if r is None:
            self._set_status("no result to send", error=True)
            return
        m = r.mechanics
        name = f"{self.controller.directory.name} true σ–ε" if self.controller.directory else "true σ–ε"
        self._send_to_figures(name, m.eps_true, m.str_true)

    def _analysis_curve(self, kind: str) -> "Curve | None":
        """Provide the current stress-strain curve to the cleanup tab (or None)."""
        r = self.controller.result
        if r is None:
            return None
        m = r.mechanics
        if kind == "eng":
            return Curve(m.eps_eng.copy(), m.str_eng.copy())
        return Curve(m.eps_true.copy(), m.str_true.copy())

    # ------------------------------------------------------------------- events
    def _on_load_clicked(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select experiment directory")
        if directory:
            self.load_directory(directory)

    def load_directory(self, directory: str) -> None:
        """Load an experiment dir and refresh the whole view (also used by tests)."""
        try:
            self.controller.load(directory)
        except Exception as exc:  # bad/missing files -> tell the user, stay open
            self._set_status(f"load failed: {exc}", error=True)
            return
        self.dir_label.setText(str(self.controller.directory))
        self._plots_host.set_watermark_visible(False)
        self._populate_config()
        self._set_enabled(True)
        self._sync_timcut_line()
        self._refresh_raw()
        self._refresh_derived()

    def _on_timcut_dragged(self) -> None:
        if self._syncing:
            return
        self.controller.tim_cut = float(self.timcut_line.value())
        self.controller.recompute()
        self._update_timcut_readout()
        self._refresh_derived()

    def _on_invert(self, checked: bool) -> None:
        self.controller.invert_signals = checked
        self.controller.recompute()
        self._refresh_raw()
        self._refresh_derived()

    def _on_nu(self, value: float) -> None:
        self.controller.nu = value
        self.controller.recompute()
        self._refresh_derived()

    def _on_shift(self, value: int) -> None:
        if self._syncing:
            return
        self.controller.reflect_shift = int(value)
        self.controller.recompute()
        self._refresh_derived()

    def _on_graph_toggled(self, item: QtWidgets.QListWidgetItem) -> None:
        pw = self._plot_by_key.get(item.text())
        if pw is not None:
            pw.setVisible(item.checkState() == QtCore.Qt.Checked)

    def _apply_config_edits(self) -> None:
        if not self.controller.loaded or self._syncing:
            return
        f = self._cfg_fields
        try:
            exp = ExpConfig(
                nlong=self.controller.exp.nlong,
                npoint=int(round(float(f["npoint"].text()))),
                tpp=self.controller.exp.tpp,  # signal-derived; not user-editable
                diam_bar=float(f["diam_bar"].text()),
                E=float(f["E"].text()), x1=float(f["x1"].text()), x2=float(f["x2"].text()),
                c0=float(f["c0"].text()), gfact=float(f["gfact"].text()),
                vbridge=float(f["vbridge"].text()),
            )
            spec = SpecConfig(
                diam_spec=float(f["diam_spec"].text()), long_spec=float(f["long_spec"].text()),
                tdelay_us=float(f["tdelay_us"].text()), pretr_pct=float(f["pretr_pct"].text()),
            )
            damp_f = float(f["damp_f"].text())
        except ValueError:
            self._set_status("invalid configuration value", error=True)
            return
        self.controller.update_config(exp, spec, damp_f)
        self._sync_timcut_line()
        self._refresh_raw()
        self._refresh_derived()
        self._update_derived_readout()

    def _on_save_config(self) -> None:
        if not self.controller.loaded:
            return
        try:
            path = self.controller.save_config()
        except Exception as exc:  # surfaced in the status bar, never silently dropped
            self._set_status(f"could not save config: {exc}", error=True)
            return
        self._update_derived_readout()  # written distances are no longer flagged as estimates
        self._set_status(f"Saved config overrides to {path}.")

    def _on_revert_config(self) -> None:
        if not self.controller.loaded:
            return
        self.controller.reload_config()
        self._populate_config()
        self._sync_timcut_line()
        self._refresh_raw()
        self._refresh_derived()
        self._set_status("Reverted configuration to the files on disk.")

    def _on_reestimate_distances(self) -> None:
        """Re-derive x1 and x2 from the signals, overriding any configured (possibly stale) values."""
        if not self.controller.loaded:
            return
        try:
            est = self.controller.estimate_geometry()
        except Exception as exc:
            self._set_status(f"could not estimate distances: {exc}", error=True)
            return
        self.controller.set_distances(
            x1=est.x1, x2=est.x2, x1_estimated=True, x2_estimated=True)
        self._populate_config()
        self._sync_timcut_line()
        self._refresh_raw()
        self._refresh_derived()
        self._set_status(
            f"Re-estimated: x1={est.x1:.4g} m (corr {est.x1_corr:.2f}), "
            f"x2={est.x2:.4g} m (SNR {est.x2_snr:.0f}) — verify & Save to keep.")

    def _on_pick_x2_toggled(self, checked: bool) -> None:
        """Enter/leave the 2-click x2 pick mode on the Signals plot."""
        if not self.controller.loaded:
            self.pick_x2_btn.setChecked(False)
            return
        if checked:
            self._x2_pick_pts = []
            self._set_status("Pick x2: click the INCIDENT pulse arrival on the Signals plot…")
        else:
            self._cancel_x2_pick()

    def _cancel_x2_pick(self) -> None:
        self._x2_pick_pts = None
        for ln in self._x2_pick_lines:
            self._signals_plot.removeItem(ln)
        self._x2_pick_lines.clear()
        self.pick_x2_btn.setChecked(False)  # emits toggled, not the connected clicked → no re-entry

    def _on_signals_clicked(self, event: object) -> None:
        if self._x2_pick_pts is None:
            return  # not in pick mode
        vb = self._signals_plot.getPlotItem().vb
        if not vb.sceneBoundingRect().contains(event.scenePos()):
            return  # click landed outside the plot area
        t = float(vb.mapSceneToView(event.scenePos()).x())
        self._x2_pick_pts.append(t)
        line = pg.InfiniteLine(pos=t, angle=90,
                               pen=pg.mkPen(self.theme.timcut, width=1, style=QtCore.Qt.DotLine))
        self._signals_plot.addItem(line)
        self._x2_pick_lines.append(line)
        if len(self._x2_pick_pts) < 2:
            self._set_status("Pick x2: now click the TRANSMITTED pulse arrival…")
            return
        t_inc, t_tra = self._x2_pick_pts
        x2 = self.controller.x2_from_picks(t_inc, t_tra)
        self._cancel_x2_pick()
        self._populate_config()
        self._refresh_derived()
        self._set_status(f"x2 set from picks: {x2:.4g} m (Δt={t_tra - t_inc:.3e} s).")

    def _on_export_clicked(self) -> None:
        directory = QtWidgets.QFileDialog.getExistingDirectory(self, "Select output directory")
        if not directory:
            return
        try:
            written = self.controller.export(directory)
        except Exception as exc:
            self._set_status(f"export failed: {exc}", error=True)
            return
        self._set_status(f"wrote {len(written)} files to {directory}")

    # ------------------------------------------------------------------ refresh
    def _refresh_raw(self) -> None:
        if not self.controller.loaded:
            return
        inc, tra = self.controller.display_signals()
        self.c_inc.setData(self.controller.time, inc)
        self.c_tra.setData(self.controller.time, tra)

    def _refresh_derived(self) -> None:
        r = self.controller.result
        if r is None:
            for curve in (self.w_inc, self.w_ref, self.w_tra, self.cc_inc, self.cc_ref,
                          self.cc_tra, self.f_in, self.f_out, self.f_diff, self.ss_eng,
                          self.ss_true):
                curve.setData([], [])
            self.explore_panel.refresh()
            self._set_status(self.controller.error or "no result", error=True)
            return

        wt = r.windowed.time
        self.w_inc.setData(wt, r.windowed.incident)
        self.w_ref.setData(wt, r.windowed.reflected)
        self.w_tra.setData(wt, r.windowed.transmitted)
        self.cc_inc.setData(wt, r.aligned.incident)
        self.cc_ref.setData(wt, r.aligned.reflected)
        self.cc_tra.setData(wt, r.aligned.transmitted)

        m = r.mechanics
        self.f_in.setData(m.time, m.f_in)
        self.f_out.setData(m.time, m.f_out)
        self.f_diff.setData(m.time, m.f_in - m.f_out)
        self.ss_eng.setData(m.eps_eng, m.str_eng)
        self.ss_true.setData(m.eps_true, m.str_true)
        if not self._fdiff_region_init and len(m.time) > 1:
            span = m.time[-1] - m.time[0]
            with _sync(self):
                self.fdiff_region.setRegion((m.time[0] + 0.25 * span, m.time[0] + 0.75 * span))
            self._fdiff_region_init = True
        self._update_fdiff_avg()
        self.explore_panel.refresh()
        self._set_status(f"v_striker ≈ {float(np.max(m.v_striker)):.1f} m/s · {len(m.time)} pts")

    def _update_fdiff_avg(self) -> None:
        r = self.controller.result
        if r is None:
            return
        m = r.mechanics
        t0, t1 = self.fdiff_region.getRegion()
        mask = (m.time >= t0) & (m.time <= t1)
        diff = (m.f_in - m.f_out)[mask]
        self._fdiff_plot.suffix = (
            f"  —  mean Δf = {float(diff.mean()):.1f} N  ({mask.sum()} pts in selection)"
            if diff.size else "  —  (empty selection)"
        )
        self._fdiff_plot.widget.getPlotItem().setTitle(
            self._fdiff_plot.title + self._fdiff_plot.suffix,
            color=self.theme.plot_fg, size="10pt",
        )

    # -------------------------------------------------------------------- utils
    def _sync_timcut_line(self) -> None:
        lo, hi = self.controller.tim_cut_range()
        with _sync(self):
            self.timcut_line.setBounds((lo, hi))
            self.timcut_line.setValue(self.controller.tim_cut)
        self._update_timcut_readout()

    def _update_timcut_readout(self) -> None:
        self.timcut_readout.setText(f"tim_cut: {self.controller.tim_cut:.3e} s")

    def _populate_config(self) -> None:
        e, s = self.controller.exp, self.controller.spec
        values = {
            "npoint": e.npoint, "diam_bar": e.diam_bar, "E": e.E,
            "x1": e.x1, "x2": e.x2, "c0": e.c0, "gfact": e.gfact, "vbridge": e.vbridge,
            "diam_spec": s.diam_spec, "long_spec": s.long_spec,
            "tdelay_us": s.tdelay_us, "pretr_pct": s.pretr_pct, "damp_f": self.controller.damp_f,
        }
        for key, field in self._cfg_fields.items():
            field.blockSignals(True)
            field.setText(f"{values[key]:g}")
            field.blockSignals(False)
        self._update_derived_readout()

    def _update_derived_readout(self) -> None:
        """Show the signal-derived tpp and flag any auto-estimated (not configured) distances."""
        c = self.controller
        parts = [f"tpp (from signal): {c.exp.tpp:.3e} s"]
        auto = [k for k, on in (("x1", c.x1_estimated), ("x2", c.x2_estimated)) if on]
        if auto:
            parts.append("⚠ auto-estimated, verify: " + ", ".join(
                f"{k}={getattr(c.exp, k):.4g} m" for k in auto))
        self.derived_readout.setText("\n".join(parts))

    def _set_enabled(self, enabled: bool) -> None:
        widgets = [self.invert_chk, self.nu_spin, self.shift_spin, self.shift_slider,
                   self.export_btn, self.revert_btn, self.save_cfg_btn, self.send_fig_btn,
                   self.reestimate_btn, self.pick_x2_btn,
                   *self._cfg_fields.values()]
        for w in widgets:
            w.setEnabled(enabled)

    def _set_status(self, text: str, *, error: bool = False) -> None:
        color = self.theme.red if error else self.theme.text_muted
        self.status.setStyleSheet(f"color: {color};")
        self.status.setText(text)


class _sync:
    """Context manager suppressing re-entrant handlers during programmatic updates."""

    def __init__(self, window: MainWindow) -> None:
        self.window = window

    def __enter__(self) -> None:
        self.window._syncing = True

    def __exit__(self, *exc: object) -> None:
        self.window._syncing = False


def _make_splash() -> "QtWidgets.QSplashScreen | None":
    """A banner splash shown while the window builds, or None if the asset is unavailable."""
    if not _BANNER_PATH.exists():
        return None
    pm = QtGui.QPixmap(str(_BANNER_PATH))
    if pm.isNull():
        return None
    splash = QtWidgets.QSplashScreen(
        pm.scaledToWidth(560, QtCore.Qt.SmoothTransformation), QtCore.Qt.WindowStaysOnTopHint)
    splash.setWindowIcon(app_icon())
    return splash


def main(argv: list[str] | None = None) -> int:
    app = QtWidgets.QApplication(argv if argv is not None else sys.argv)
    app.setStyle("Fusion")  # consistent QSS rendering of spinbox/combo controls across OSes
    app.setWindowIcon(app_icon())  # dock/taskbar icon (the .app bundle uses Hopki.icns)

    splash = _make_splash()
    if splash is not None:
        splash.show()
        app.processEvents()  # paint the splash before the (slower) window build

    window = MainWindow()
    if len(app.arguments()) > 1:
        candidate = Path(app.arguments()[1])
        if candidate.is_dir():
            window.load_directory(str(candidate))
    window.show()
    if splash is not None:  # keep the splash up briefly, then reveal the ready window
        QtCore.QTimer.singleShot(2500, lambda: splash.finish(window))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
