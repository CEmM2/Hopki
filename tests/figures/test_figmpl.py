"""Tests for the matplotlib (+ SciencePlots) publication export."""

from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path
from unittest import mock

import numpy as np

from hopki import figmpl
from hopki.figio import CurveStyle, FigureCurve, FigureDoc


def _doc(**kw) -> FigureDoc:
    t = np.linspace(0, 1, 40)
    c = FigureCurve("A", t, np.sin(6 * t), CurveStyle(symbol="o", line_style="dash"))
    return FigureDoc(curves=[c], x_label="strain", y_label="stress [MPa]", **kw)


class FigMplTests(unittest.TestCase):
    def test_available_styles_nonempty_and_have_builtins(self) -> None:
        styles = figmpl.available_styles()
        self.assertTrue(styles)
        self.assertIn("default", styles)  # matplotlib built-in is always present

    def test_export_png_and_pdf(self) -> None:
        doc = _doc(style="default", tick_fontsize=9, label_fontsize=13)
        with tempfile.TemporaryDirectory() as d:
            png = figmpl.export(doc, Path(d) / "fig.png")
            pdf = figmpl.export(doc, Path(d) / "fig.pdf")
            self.assertTrue(png.exists() and png.stat().st_size > 1000)
            self.assertTrue(pdf.exists() and pdf.stat().st_size > 1000)

    def test_render_returns_figure_with_axis_labels(self) -> None:
        fig = figmpl.render(_doc(style="default", title="Fig 1"))
        ax = fig.axes[0]
        self.assertEqual(ax.get_xlabel(), "strain")
        self.assertEqual(ax.get_ylabel(), "stress [MPa]")
        self.assertEqual(ax.get_title(), "Fig 1")

    @unittest.skipUnless("science" in figmpl.available_styles(), "SciencePlots not installed")
    def test_figure_size_overrides_style(self) -> None:
        # Regression: SciencePlots forces a ~3.5x2.6in canvas; doc.fig_* must win so large
        # fonts don't overflow/clip. The rendered figure must match the requested size.
        fig = figmpl.render(_doc(style="science", fig_width=6.4, fig_height=4.8))
        w, h = fig.get_size_inches()
        self.assertAlmostEqual(w, 6.4, places=6)
        self.assertAlmostEqual(h, 4.8, places=6)

    def test_latex_available_returns_bool(self) -> None:
        self.assertIsInstance(figmpl.latex_available(), bool)

    def test_export_falls_back_to_mathtext_without_tex(self) -> None:
        # On a machine with no TeX, a use_latex=True doc must still export (degrade to
        # mathtext) and warn — not crash. Force the "no TeX" branch regardless of host.
        doc = _doc(style="default", use_latex=True)
        with mock.patch.object(figmpl, "latex_available", return_value=False):
            with tempfile.TemporaryDirectory() as d, warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                out = figmpl.export(doc, Path(d) / "fallback.png")
                self.assertTrue(out.exists() and out.stat().st_size > 1000)
            messages = [str(w.message) for w in caught if issubclass(w.category, RuntimeWarning)]
            self.assertTrue(any("mathtext" in m for m in messages), messages)

    def test_effective_usetex_off_when_not_requested(self) -> None:
        # use_latex=False must never warn or attempt LaTeX, even where TeX is installed.
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            self.assertFalse(figmpl._effective_usetex(_doc(use_latex=False)))

    @unittest.skipUnless("science" in figmpl.available_styles(), "SciencePlots not installed")
    def test_science_style_exports(self) -> None:
        # science style without LaTeX (use_latex=False -> mathtext) should always render.
        doc = _doc(style="science", use_latex=False)
        with tempfile.TemporaryDirectory() as d:
            out = figmpl.export(doc, Path(d) / "sci.png")
            self.assertTrue(out.exists() and out.stat().st_size > 1000)


if __name__ == "__main__":
    unittest.main()
