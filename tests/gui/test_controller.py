"""Tests for the GUI's headless controller (no Qt) plus a guarded offscreen app smoke test."""

from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hopki.gui.controller import Controller

FIXTURE = Path(__file__).resolve().parents[1] / "analysis"
GOLD = FIXTURE / "gold"
HAS_PYSIDE = importlib.util.find_spec("PySide6") is not None


class ControllerTests(unittest.TestCase):
    def test_load_sets_defaults_and_result(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        self.assertTrue(c.loaded)
        lo, hi = c.tim_cut_range()
        self.assertLess(lo, hi)
        self.assertGreaterEqual(c.tim_cut, lo)
        self.assertLessEqual(c.tim_cut, hi)
        self.assertIsNotNone(c.result)
        self.assertIsNone(c.error)

    def test_gold_parameters_reproduce_gold(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        c.invert_signals = True
        c.reflect_shift = 3
        c.tim_cut = float(np.loadtxt(GOLD / "tim_cut"))
        c.recompute()
        self.assertIsNone(c.error)
        f_in = c.result.mechanics.f_in
        gold_f_in = np.loadtxt(GOLD / "f_in")[:, 1]
        np.testing.assert_allclose(f_in, gold_f_in, rtol=1e-4, atol=1e-2)

    def test_legacy_fixture_distances_not_flagged_estimated(self) -> None:
        c = Controller()
        c.load(FIXTURE)  # legacy positional config supplies x1/x2 -> not estimated
        self.assertFalse(c.x1_estimated)
        self.assertFalse(c.x2_estimated)

    def test_toml_without_distances_flags_estimated(self) -> None:
        import shutil

        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        for name in ("WAVE0030.FLT", "WAVE0031.FLT"):
            shutil.copy(FIXTURE / name, d / name)
        (d / "hopki.toml").write_text("[bar]\nc0 = 4800\n")
        c = Controller()
        c.load(d)
        self.assertTrue(c.x1_estimated)
        self.assertTrue(c.x2_estimated)
        self.assertAlmostEqual(c.exp.x1, 0.558, delta=0.01)
        self.assertIsNone(c.error)

    def test_estimate_geometry_and_set_distances(self) -> None:
        c = Controller()
        c.load(FIXTURE)  # legacy fixture: x1/x2 configured, not flagged
        est = c.estimate_geometry()  # re-derive over configured values
        self.assertAlmostEqual(est.x1, 0.558, delta=0.01)
        c.set_distances(x1=est.x1, x2=est.x2, x1_estimated=True, x2_estimated=True)
        self.assertTrue(c.x1_estimated)
        self.assertTrue(c.x2_estimated)
        self.assertAlmostEqual(c.exp.x1, est.x1)
        self.assertIsNone(c.error)  # recomputed cleanly

    def test_x2_from_picks(self) -> None:
        c = Controller()
        c.load(FIXTURE)  # x1=0.558, c0=4800, tdelay=0
        # Choose a transmitted arrival that should back out to x2 = 0.230.
        t_inc = 0.0
        t_tra = (c.exp.x1 + 0.230) / c.exp.c0
        x2 = c.x2_from_picks(t_inc, t_tra)
        self.assertAlmostEqual(x2, 0.230, places=6)
        self.assertAlmostEqual(c.exp.x2, 0.230, places=6)
        self.assertFalse(c.x2_estimated)  # a deliberate pick is verified, not an estimate

    def test_x2_from_picks_clamps_negative(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        # transmitted "before" incident by the geometry -> unphysical -> clamp to 0
        self.assertEqual(c.x2_from_picks(1e-4, 0.0), 0.0)

    def test_recompute_never_raises_on_bad_tim_cut(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        c.tim_cut = 1.0  # absurd: windows fall out of range
        c.recompute()  # must capture the error, not raise
        self.assertIsNone(c.result)
        self.assertIsNotNone(c.error)

    def test_tim_cut_range_spans_record(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        lo, hi = c.tim_cut_range()
        self.assertEqual(lo, 0.0)
        # full record, not the old reflected-window-limited bound (~4.25e-5)
        self.assertAlmostEqual(hi, (c.exp.nlong - 1) * c.exp.tpp)
        self.assertGreater(hi, 4.25e-5)

    def test_reload_config_restores_files(self) -> None:
        import dataclasses

        c = Controller()
        c.load(FIXTURE)
        original_npoint = c.exp.npoint
        c.update_config(dataclasses.replace(c.exp, npoint=123), c.spec, c.damp_f)
        self.assertEqual(c.exp.npoint, 123)
        c.reload_config()
        self.assertEqual(c.exp.npoint, original_npoint)
        self.assertIsNone(c.error)

    def test_display_signals_respects_polarity(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        inc_pos, _ = c.display_signals()
        c.invert_signals = True
        inc_neg, _ = c.display_signals()
        np.testing.assert_allclose(inc_neg, -inc_pos)

    def test_update_config_reclamps_and_recomputes(self) -> None:
        import dataclasses

        c = Controller()
        c.load(FIXTURE)
        exp2 = dataclasses.replace(c.exp, npoint=400)
        c.update_config(exp2, c.spec, c.damp_f)
        self.assertEqual(c.exp.npoint, 400)
        self.assertIsNone(c.error)
        self.assertEqual(len(c.result.windowed.incident), 400)

    def test_export_writes_files(self) -> None:
        c = Controller()
        c.load(FIXTURE)
        c.invert_signals = True
        c.reflect_shift = 3
        c.recompute()
        with tempfile.TemporaryDirectory() as d:
            written = c.export(d)
            self.assertTrue(any(p.name == "s_e_true" for p in written))


@unittest.skipUnless(HAS_PYSIDE, "PySide6 not installed (install with: uv sync --extra gui)")
class AppSmokeTests(unittest.TestCase):
    def _make_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6 import QtWidgets

        from hopki.gui.app import MainWindow

        QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        window = MainWindow()
        window.load_directory(str(FIXTURE))
        return window

    def test_window_constructs_and_loads(self) -> None:
        window = self._make_window()
        self.assertIsNotNone(window.controller.result)
        window._on_invert(True)
        window._on_shift(3)
        self.assertIsNone(window.controller.error)
        window.close()

    def test_theme_switch(self) -> None:
        window = self._make_window()
        for name in ("Light", "Dark"):
            window.apply_theme(name)
            self.assertEqual(window.theme.name, name)
        window.close()

    def test_cleanup_tab_operations(self) -> None:
        window = self._make_window()
        panel = window.cleanup_panel
        panel._pull("true")
        self.assertIsNotNone(panel._curve)
        n0 = len(panel._curve.e)
        panel._zero()
        self.assertEqual(panel._curve.e[0], 0.0)
        panel._cut()  # cut at the pick line (median) -> fewer points
        self.assertLess(len(panel._curve.e), n0)
        panel._back()  # undo
        self.assertEqual(len(panel._curve.e), n0)
        # negate an axis
        s_before = panel._curve.s.copy()
        panel._negate("stress")
        np.testing.assert_allclose(panel._curve.s, -s_before)

        # scale σ by a constant (mutates the data; undoable with Back)
        s_pre = panel._curve.s.copy()
        e_pre = panel._curve.e.copy()
        panel.factor_edit.setText("1e-6")
        panel._scale("stress")
        np.testing.assert_allclose(panel._curve.s, s_pre * 1e-6)
        np.testing.assert_allclose(panel._curve.e, e_pre)  # strain untouched
        panel._back()
        np.testing.assert_allclose(panel._curve.s, s_pre)

        # scale ε by a constant
        panel.factor_edit.setText("100")
        panel._scale("strain")
        np.testing.assert_allclose(panel._curve.e, e_pre * 100.0)
        panel._back()
        np.testing.assert_allclose(panel._curve.e, e_pre)

        # invalid / zero factor is rejected (curve unchanged)
        guard = panel._curve.s.copy()
        panel.factor_edit.setText("0")
        panel._scale("stress")
        np.testing.assert_allclose(panel._curve.s, guard)
        panel.factor_edit.setText("not a number")
        panel._scale("strain")
        np.testing.assert_allclose(panel._curve.e, e_pre)

        # shift σ / ε by a constant (undoable with Back)
        s_pre2 = panel._curve.s.copy()
        e_pre2 = panel._curve.e.copy()
        panel.shift_edit.setText("-5")
        panel._shift("stress")
        np.testing.assert_allclose(panel._curve.s, s_pre2 - 5.0)
        np.testing.assert_allclose(panel._curve.e, e_pre2)  # strain untouched
        panel._back()
        np.testing.assert_allclose(panel._curve.s, s_pre2)
        panel.shift_edit.setText("0.01")
        panel._shift("strain")
        np.testing.assert_allclose(panel._curve.e, e_pre2 + 0.01)
        panel._back()
        np.testing.assert_allclose(panel._curve.e, e_pre2)

        # invalid shift amount is rejected (curve unchanged)
        panel.shift_edit.setText("oops")
        panel._shift("stress")
        np.testing.assert_allclose(panel._curve.s, s_pre2)
        window.close()

    def test_cleanup_to_true(self) -> None:
        from hopki import figcorr

        window = self._make_window()
        panel = window.cleanup_panel

        # Pulling a true curve disables conversion (would double-convert).
        panel._pull("true")
        self.assertFalse(panel.to_true_btn.isEnabled())
        true_ref = (panel._curve.e.copy(), panel._curve.s.copy())

        # Pulling engineering enables it; converting reproduces the analysis true curve.
        panel._pull("eng")
        self.assertTrue(panel.to_true_btn.isEnabled())
        eng_e, eng_s = panel._curve.e.copy(), panel._curve.s.copy()
        panel._to_true()
        self.assertEqual(panel._kind, "true")
        self.assertFalse(panel.to_true_btn.isEnabled())   # now true -> disabled
        np.testing.assert_allclose(panel._curve.e, true_ref[0], rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(panel._curve.s, true_ref[1], rtol=1e-7, atol=1e-3)
        # and it matches the pure op
        ref = figcorr.to_true(figcorr.Curve(eng_e, eng_s))
        np.testing.assert_allclose(panel._curve.e, ref.e)
        np.testing.assert_allclose(panel._curve.s, ref.s)

        # Back restores the engineering curve and re-enables conversion.
        panel._back()
        self.assertEqual(panel._kind, "eng")
        self.assertTrue(panel.to_true_btn.isEnabled())
        np.testing.assert_allclose(panel._curve.e, eng_e)

        # A loaded/explore curve is convertible (unknown kind, user's responsibility).
        panel.set_curve_data(eng_e, eng_s, "from explore")
        self.assertTrue(panel.to_true_btn.isEnabled())
        window.close()

    def test_cleanup_interactive_smoothing(self) -> None:
        window = self._make_window()
        panel = window.cleanup_panel
        panel._pull("true")
        s_before = panel._curve.s.copy()

        # Enter cutoff-preview mode: PSD shown, filtered overlay populated, nothing committed.
        panel._begin_smooth()
        self.assertTrue(panel._smoothing)
        self.assertFalse(panel.psd_plot.isHidden())  # shown (isVisible needs a shown window)
        self.assertGreater(len(panel.psd_curve.getData()[0]), 0)
        self.assertGreater(len(panel.preview_curve.getData()[0]), 0)
        np.testing.assert_array_equal(panel._curve.s, s_before)  # still untouched

        # Dragging the cutoff line keeps the spinbox in sync and updates the preview only.
        panel.cutoff_line.setValue(0.15)
        self.assertAlmostEqual(panel.cutoff_spin.value(), 0.15, places=6)
        np.testing.assert_array_equal(panel._curve.s, s_before)

        # Cancel leaves the curve unchanged and hides the spectrum.
        panel._cancel_smooth()
        self.assertFalse(panel._smoothing)
        self.assertTrue(panel.psd_plot.isHidden())
        np.testing.assert_array_equal(panel._curve.s, s_before)

        # Re-enter and Apply: now the curve is filtered (variance drops) and undoable.
        panel._begin_smooth()
        panel.cutoff_line.setValue(0.1)
        panel._apply_smooth()
        self.assertFalse(panel._smoothing)
        self.assertEqual(len(panel._curve.s), len(s_before))
        self.assertLess(panel._curve.s.var(), s_before.var())
        panel._back()
        np.testing.assert_allclose(panel._curve.s, s_before)
        window.close()

    def test_cleanup_save_defaults(self) -> None:
        import shutil

        from PySide6 import QtWidgets

        from hopki import figcorr

        window = self._make_window()
        panel = window.cleanup_panel

        # Analysis pull -> save next to the experiment, named like the analysis output.
        panel._pull("true")
        self.assertEqual(panel.default_save_path(), str(FIXTURE / "s_e_true_corr"))
        panel._pull("eng")
        self.assertEqual(panel.default_save_path(), str(FIXTURE / "s_e_eng_corr"))

        # Loaded file -> default back to the folder it came from, <stem>_corr.
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        src = d / "mycurve.txt"
        figcorr.save_curve(panel._curve, str(src))
        orig = QtWidgets.QFileDialog.getOpenFileName
        QtWidgets.QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(src), ""))
        try:
            panel._on_load()
        finally:
            QtWidgets.QFileDialog.getOpenFileName = orig
        self.assertEqual(panel.default_save_path(), str(d / "mycurve_corr"))
        window.close()

    def test_config_edit_and_graph_toggle(self) -> None:
        from PySide6 import QtCore

        window = self._make_window()
        window._cfg_fields["npoint"].setText("400")
        window._apply_config_edits()
        self.assertEqual(window.controller.exp.npoint, 400)
        self.assertIsNone(window.controller.error)

        item = window.graphs_list.item(0)
        item.setCheckState(QtCore.Qt.Unchecked)
        self.assertTrue(window._plot_by_key[item.text()].isHidden())
        # force-difference plot exists and has data
        self.assertGreater(len(window.f_diff.getData()[0]), 0)
        window.close()

    def test_revert_config_and_explore_and_fdiff_region(self) -> None:
        window = self._make_window()
        # revert restores npoint after an edit
        original = window.controller.exp.npoint
        window._cfg_fields["npoint"].setText("400")
        window._apply_config_edits()
        self.assertEqual(window.controller.exp.npoint, 400)
        window._on_revert_config()
        self.assertEqual(window.controller.exp.npoint, original)
        self.assertEqual(window._cfg_fields["npoint"].text(), f"{original:g}")

        # force-difference region average updates the plot title suffix
        window._update_fdiff_avg()
        self.assertIn("mean Δf", window._fdiff_plot.suffix)

        # explore tab: switch quantity + flip x axis (true strain), curve has data
        ex = window.explore_panel
        ex.y_combo.setCurrentIndex(1)  # v_in
        ex._toggle_x()  # x -> strain
        self.assertEqual(ex._x_mode, "strain")
        np.testing.assert_allclose(ex._cur_x, window.controller.result.mechanics.eps_true)
        self.assertGreater(len(ex.curve.getData()[0]), 0)

        # per-axis negate toggles flip the displayed data
        x_before = ex._cur_x.copy()
        ex.neg_x_btn.setChecked(True)
        np.testing.assert_allclose(ex._cur_x, -x_before)

        # send-to-cleanup hands the shown curve to the cleanup tab and switches to it
        ex.send_btn.click()
        np.testing.assert_allclose(window.cleanup_panel._curve.e, ex._cur_x)
        np.testing.assert_allclose(window.cleanup_panel._curve.s, ex._cur_y)
        self.assertIs(window.tabs.currentWidget(), window.cleanup_panel)
        window.close()

    def test_reestimate_button_and_pick_mode(self) -> None:
        window = self._make_window()
        # Re-estimate overrides the configured distances and flags them for verification.
        window.reestimate_btn.click()
        self.assertTrue(window.controller.x1_estimated)
        self.assertTrue(window.controller.x2_estimated)
        self.assertAlmostEqual(window.controller.exp.x1, 0.558, delta=0.01)
        self.assertIn("auto-estimated", window.derived_readout.text())

        # Toggle the 2-click pick mode on, then cancel it via the toggle.
        window.pick_x2_btn.click()  # check -> enter pick mode
        self.assertEqual(window._x2_pick_pts, [])
        window.pick_x2_btn.click()  # uncheck -> cancel
        self.assertIsNone(window._x2_pick_pts)
        self.assertFalse(window.pick_x2_btn.isChecked())
        window.close()

    def test_send_to_figures(self) -> None:
        window = self._make_window()
        # from Analysis: σ–ε → Figures
        n0 = len(window.figures_panel.doc.curves)
        window._on_send_sigeps()
        self.assertEqual(len(window.figures_panel.doc.curves), n0 + 1)
        self.assertIs(window.tabs.currentWidget(), window.figures_panel)
        np.testing.assert_allclose(
            window.figures_panel.doc.curves[-1].x, window.controller.result.mechanics.eps_true)

        # from Explore: Send to figures
        window.explore_panel.send_fig_btn.click()
        self.assertEqual(len(window.figures_panel.doc.curves), n0 + 2)
        window.close()

    def test_figures_to_cleanup_roundtrip(self) -> None:
        window = self._make_window()
        # put a σ–ε curve on the Figures tab, select it, send it to cleanup
        window._on_send_sigeps()
        fp = window.figures_panel
        fp.curve_list.setCurrentRow(len(fp.doc.curves) - 1)
        sel = fp.doc.curves[fp._selected]
        x, y = sel.shown()
        fp.send_selected_to_cleanup()
        # cleanup received it and the app switched to the cleanup tab
        self.assertIs(window.tabs.currentWidget(), window.cleanup_panel)
        np.testing.assert_allclose(window.cleanup_panel._curve.e, x)
        np.testing.assert_allclose(window.cleanup_panel._curve.s, y)
        window.close()


if __name__ == "__main__":
    unittest.main()
