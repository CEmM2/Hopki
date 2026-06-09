"""Offscreen smoke tests for the Figures tab (FiguresPanel)."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

HAS_PYSIDE = importlib.util.find_spec("PySide6") is not None


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not installed (install with: uv sync --extra gui)")
class FiguresPanelTests(unittest.TestCase):
    def _panel(self, send_to_cleanup=None):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6 import QtWidgets

        from hopki.gui.figures import FiguresPanel

        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        return FiguresPanel(send_to_cleanup=send_to_cleanup)

    def test_add_style_trim_save_load_export_delete(self) -> None:
        panel = self._panel()
        t = np.linspace(0, 1, 20)
        panel.add_curve("A", t, np.sin(6 * t))
        panel.add_curve("B", t, np.cos(6 * t))
        self.assertEqual(len(panel.doc.curves), 2)

        # style edit on the first curve
        panel.curve_list.setCurrentRow(0)
        panel.width_spin.setValue(4.0)
        panel.line_combo.setCurrentText("dash")
        self.assertEqual(panel.doc.curves[0].style.line_width, 4.0)
        self.assertEqual(panel.doc.curves[0].style.line_style, "dash")

        # trim the first curve's shown range
        panel.doc.curves[0].x_lo, panel.doc.curves[0].x_hi = 0.2, 0.8
        xs, _ = panel.doc.curves[0].shown()
        self.assertLess(len(xs), 20)

        # axes edits
        panel.xlabel_edit.setText("strain")
        panel.xfmt_edit.setText("%.3f")
        panel._apply_axes_edits()
        self.assertEqual(panel.doc.x_label, "strain")
        self.assertEqual(panel._xaxis.fmt, "%.3f")

        with tempfile.TemporaryDirectory() as d:
            npz = Path(d) / "fig.npz"
            panel.save(str(npz))
            panel.load_figure_file(str(npz))   # parallel load: appends the 2 saved curves
            self.assertEqual(len(panel.doc.curves), 4)

            png = Path(d) / "out.png"
            panel.export_png(str(png))
            self.assertTrue(png.exists())
            self.assertTrue(png.with_suffix(".npz").exists())  # data alongside the image

        # delete a curve
        panel.curve_list.setCurrentRow(0)
        panel._on_delete()
        self.assertEqual(len(panel.doc.curves), 3)

    def test_scale_x_and_y(self) -> None:
        panel = self._panel()
        t = np.linspace(0, 1, 10)
        panel.add_curve("A", t, t)
        panel.curve_list.setCurrentRow(0)

        # scale x by 1000 and y by 2 -> rendered data is scaled, model updated
        panel.xscale_edit.setText("1000")
        panel._apply_style()
        panel.yscale_edit.setText("2")
        panel._apply_style()
        c = panel.doc.curves[0]
        self.assertEqual((c.x_scale, c.y_scale), (1000.0, 2.0))
        xr, yr = panel._items[0].getData()
        np.testing.assert_allclose(xr, t * 1000.0)
        np.testing.assert_allclose(yr, t * 2.0)

        # invalid / zero scale is rejected (keeps the previous value, reflected in the field)
        panel.xscale_edit.setText("0")
        panel._apply_style()
        self.assertEqual(panel.doc.curves[0].x_scale, 1000.0)
        panel.xscale_edit.setText("not a number")
        panel._apply_style()
        self.assertEqual(panel.doc.curves[0].x_scale, 1000.0)
        self.assertEqual(panel.xscale_edit.text(), "1000")

        # trim stays in raw x and survives a scale change (selects the same points)
        panel.doc.curves[0].x_lo, panel.doc.curves[0].x_hi = 0.2, 0.5
        xr, _ = panel.doc.curves[0].shown()
        self.assertTrue(np.all((xr >= 0.2 * 1000.0 - 1e-9) & (xr <= 0.5 * 1000.0 + 1e-9)))

    def test_publication_export_settings_and_matplotlib_export(self) -> None:
        panel = self._panel()
        t = np.linspace(0, 1, 20)
        panel.add_curve("A", t, np.sin(6 * t))

        # the export controls feed FigureDoc
        panel.style_combo.setCurrentText("default")
        panel.latex_chk.setChecked(False)
        panel.tickfs_spin.setValue(9.0)
        panel.labelfs_spin.setValue(13.0)
        panel.legendfs_spin.setValue(8.0)
        panel._apply_export_edits()
        self.assertEqual(panel.doc.style, "default")
        self.assertFalse(panel.doc.use_latex)
        self.assertEqual(panel.doc.label_fontsize, 13.0)

        # export now goes through matplotlib (PNG + PDF) with an .npz sidecar
        with tempfile.TemporaryDirectory() as d:
            panel.export_png(str(Path(d) / "fig.png"))
            self.assertTrue((Path(d) / "fig.png").exists())
            self.assertTrue((Path(d) / "fig.npz").exists())
            panel.export_png(str(Path(d) / "fig.pdf"))
            self.assertTrue((Path(d) / "fig.pdf").exists())

    def test_add_multiple_curves_at_once(self) -> None:
        from PySide6 import QtWidgets

        from hopki import figcorr
        from hopki.figcorr import Curve

        panel = self._panel()
        with tempfile.TemporaryDirectory() as d:
            paths = []
            for i in range(3):
                p = Path(d) / f"c{i}.txt"
                figcorr.save_curve(Curve(np.arange(5.0), np.arange(5.0) + i), str(p))
                paths.append(str(p))
            orig = QtWidgets.QFileDialog.getOpenFileNames
            QtWidgets.QFileDialog.getOpenFileNames = staticmethod(lambda *a, **k: (paths, ""))
            try:
                panel._on_add_curve()
            finally:
                QtWidgets.QFileDialog.getOpenFileNames = orig
        self.assertEqual(len(panel.doc.curves), 3)
        self.assertEqual([c.name for c in panel.doc.curves], ["c0", "c1", "c2"])

    def test_send_to_cleanup(self) -> None:
        sent = {}

        def sink(x, y, label):
            sent["x"], sent["y"], sent["label"] = x, y, label

        panel = self._panel(send_to_cleanup=sink)
        t = np.linspace(0, 1, 10)
        panel.add_curve("mycurve", t, 2 * t)
        panel.doc.curves[0].x_scale = 100.0      # shown() applies scale
        panel.curve_list.setCurrentRow(0)
        panel.send_selected_to_cleanup()
        self.assertEqual(sent["label"], "mycurve")
        np.testing.assert_allclose(sent["x"], t * 100.0)
        np.testing.assert_allclose(sent["y"], 2 * t)


if __name__ == "__main__":
    unittest.main()
