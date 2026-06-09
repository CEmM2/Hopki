"""Explore tab — plot any derived quantity against time or true strain.

A single plot with a y-quantity dropdown (strain rate, velocities, displacements, forces,
stresses), a button to flip the x axis between time and true strain, per-axis negate toggles,
and a button to hand the currently-shown curve to the Curve cleanup tab.
"""

from __future__ import annotations

from typing import Callable

import pyqtgraph as pg
from PySide6 import QtWidgets

from hopki.twobar import Mechanics

from .theme import Theme

LINE_WIDTH = 3
MechanicsSource = Callable[[], "Mechanics | None"]
CleanupSink = Callable[[object, object, str], None]
FiguresSink = Callable[[str, object, object], None]

# (label, Mechanics attribute, y-axis label)
_QUANTITIES = [
    ("strain rate ė", "eps_rate_eng", "strain rate [1/s]"),
    ("v_in", "v_in", "velocity [m/s]"),
    ("v_out", "v_out", "velocity [m/s]"),
    ("striker velocity", "v_striker", "velocity [m/s]"),
    ("u_in", "u_in", "displacement [m]"),
    ("u_out", "u_out", "displacement [m]"),
    ("f_in", "f_in", "force [N]"),
    ("f_out", "f_out", "force [N]"),
    ("eng. stress", "str_eng", "stress [Pa]"),
    ("true stress", "str_true", "stress [Pa]"),
]


class ExplorePanel(QtWidgets.QWidget):
    """Free-form viewer for a selected quantity vs time or true strain."""

    def __init__(self, get_mechanics: MechanicsSource, send_to_cleanup: CleanupSink | None = None,
                 send_to_figures: FiguresSink | None = None) -> None:
        super().__init__()
        self._get_mechanics = get_mechanics
        self._send_to_cleanup = send_to_cleanup
        self._send_to_figures = send_to_figures
        self._x_mode = "time"  # or "strain"
        self._theme: Theme | None = None
        self._cur_x = None
        self._cur_y = None
        self._cur_label = ""

        layout = QtWidgets.QVBoxLayout(self)
        controls = QtWidgets.QHBoxLayout()
        controls.addWidget(QtWidgets.QLabel("y:"))
        self.y_combo = QtWidgets.QComboBox()
        for label, attr, _ in _QUANTITIES:
            self.y_combo.addItem(label, attr)
        self.y_combo.currentIndexChanged.connect(self.refresh)
        controls.addWidget(self.y_combo)

        self.x_btn = QtWidgets.QPushButton("x: time → strain")
        self.x_btn.clicked.connect(self._toggle_x)
        controls.addWidget(self.x_btn)

        self.neg_x_btn = QtWidgets.QPushButton("Negate x")
        self.neg_x_btn.setCheckable(True)
        self.neg_x_btn.toggled.connect(self.refresh)
        self.neg_y_btn = QtWidgets.QPushButton("Negate y")
        self.neg_y_btn.setCheckable(True)
        self.neg_y_btn.toggled.connect(self.refresh)
        controls.addWidget(self.neg_x_btn)
        controls.addWidget(self.neg_y_btn)

        self.send_btn = QtWidgets.QPushButton("Send to cleanup →")
        self.send_btn.clicked.connect(self._send)
        controls.addWidget(self.send_btn)
        self.send_fig_btn = QtWidgets.QPushButton("Send to figures →")
        self.send_fig_btn.clicked.connect(self._send_figures)
        controls.addWidget(self.send_fig_btn)
        if self._send_to_cleanup is None:
            self.send_btn.hide()
        if self._send_to_figures is None:
            self.send_fig_btn.hide()
        controls.addStretch(1)
        layout.addLayout(controls)

        self.plot = pg.PlotWidget()
        self.curve = self.plot.plot([], [])
        layout.addWidget(self.plot, stretch=1)

    # ------------------------------------------------------------------ theming
    def apply_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.plot.setBackground(theme.plot_bg)
        pi = self.plot.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.25)
        axis_pen = pg.mkPen(theme.plot_fg)
        for name in ("bottom", "left"):
            axis = pi.getAxis(name)
            axis.setPen(axis_pen)
            axis.setTextPen(axis_pen)
        self.curve.setPen(pg.mkPen(theme.accent, width=LINE_WIDTH))
        self.refresh()

    # ------------------------------------------------------------------- refresh
    def _toggle_x(self) -> None:
        self._x_mode = "strain" if self._x_mode == "time" else "time"
        self.x_btn.setText("x: strain → time" if self._x_mode == "strain" else "x: time → strain")
        self.refresh()

    def refresh(self) -> None:
        m = self._get_mechanics()
        pi = self.plot.getPlotItem()
        attr = self.y_combo.currentData()
        _, _, ylabel = _QUANTITIES[self.y_combo.currentIndex()]
        color = self._theme.plot_fg if self._theme else "k"

        if m is None or attr is None:
            self.curve.setData([], [])
            self._cur_x = self._cur_y = None
            return

        y = getattr(m, attr).copy()
        if self._x_mode == "strain":
            x, xlabel = m.eps_true.copy(), "true strain"
        else:
            x, xlabel = m.time.copy(), "time [s]"
        if self.neg_x_btn.isChecked():
            x = -x
        if self.neg_y_btn.isChecked():
            y = -y

        self._cur_x, self._cur_y = x, y
        self._cur_label = f"{self.y_combo.currentText()} vs {xlabel.split(' [')[0]}"
        # Strain (O(0.1–1)) reads better literally (0.3) than milli-prefixed (300 ×1e-3);
        # time keeps auto SI prefixes (µs/ms) where they help. Set before setData so the
        # range update recomputes the axis scale with the right flag.
        pi.getAxis("bottom").enableAutoSIPrefix(self._x_mode != "strain")
        self.curve.setData(x, y)
        pi.setTitle(self._cur_label, color=color, size="10pt")
        pi.getAxis("bottom").setLabel(xlabel, color=color)
        pi.getAxis("left").setLabel(ylabel, color=color)

    def _send(self) -> None:
        if self._cur_x is None or self._send_to_cleanup is None:
            return
        self._send_to_cleanup(self._cur_x, self._cur_y, self._cur_label)

    def _send_figures(self) -> None:
        if self._cur_x is None or self._send_to_figures is None:
            return
        self._send_to_figures(self._cur_label, self._cur_x, self._cur_y)
