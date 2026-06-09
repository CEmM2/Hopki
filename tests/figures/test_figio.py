"""Round-trip tests for the figure (.npz) save/load format."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from hopki.figio import CurveStyle, FigureCurve, FigureDoc, load_figure, save_figure


class FigIoTests(unittest.TestCase):
    def test_roundtrip_preserves_curves_styles_and_axes(self) -> None:
        c1 = FigureCurve(
            "A", np.linspace(0, 1, 10), np.linspace(0, 2, 10),
            CurveStyle(color="#ff0000", line_style="dash", line_width=3.0,
                       symbol="o", symbol_size=10.0, show_in_legend=True),
            x_lo=0.2, x_hi=0.8,
        )
        c2 = FigureCurve("B", np.arange(5.0), np.arange(5.0) ** 2)
        doc = FigureDoc(curves=[c1, c2], x_label="strain", y_label="stress [Pa]",
                        x_format="%.2f", y_format="%.1e", title="Fig 1",
                        x_limits=(0.0, 1.0), y_limits=None,
                        style="science,grid", use_latex=True, fig_width=3.5, fig_height=2.6,
                        tick_fontsize=8.0, label_fontsize=14.0, legend_fontsize=9.0)

        with tempfile.TemporaryDirectory() as d:
            path = save_figure(doc, Path(d) / "fig")
            self.assertTrue(path.exists() and path.suffix == ".npz")
            back = load_figure(path)

        self.assertEqual(len(back.curves), 2)
        self.assertEqual(back.x_label, "strain")
        self.assertEqual(back.x_format, "%.2f")
        self.assertEqual(back.x_limits, (0.0, 1.0))
        self.assertIsNone(back.y_limits)
        b1 = back.curves[0]
        self.assertEqual(b1.name, "A")
        self.assertEqual(b1.style.color, "#ff0000")
        self.assertEqual(b1.style.line_style, "dash")
        self.assertEqual(b1.style.symbol, "o")
        self.assertEqual((b1.x_lo, b1.x_hi), (0.2, 0.8))
        np.testing.assert_allclose(b1.x, c1.x)
        np.testing.assert_allclose(b1.y, c1.y)
        # publication-export settings round-trip
        self.assertEqual(back.style, "science,grid")
        self.assertTrue(back.use_latex)
        self.assertEqual((back.fig_width, back.fig_height), (3.5, 2.6))
        self.assertEqual(back.tick_fontsize, 8.0)
        self.assertEqual(back.label_fontsize, 14.0)
        self.assertEqual(back.legend_fontsize, 9.0)

    def test_shown_applies_trim(self) -> None:
        c = FigureCurve("c", np.arange(10.0), np.arange(10.0), x_lo=2, x_hi=5)
        x, y = c.shown()
        np.testing.assert_array_equal(x, [2, 3, 4, 5])
        np.testing.assert_array_equal(y, [2, 3, 4, 5])

    def test_shown_applies_scale(self) -> None:
        c = FigureCurve("c", np.arange(5.0), np.arange(5.0), x_scale=1000.0, y_scale=0.5)
        x, y = c.shown()
        np.testing.assert_array_equal(x, [0, 1000, 2000, 3000, 4000])
        np.testing.assert_array_equal(y, [0, 0.5, 1.0, 1.5, 2.0])

    def test_shown_trims_in_raw_then_scales(self) -> None:
        # Trim is in raw x; scaling is applied afterwards (so trim is scale-independent).
        c = FigureCurve("c", np.arange(10.0), np.arange(10.0), x_lo=2, x_hi=5, x_scale=10.0)
        x, y = c.shown()
        np.testing.assert_array_equal(x, [20, 30, 40, 50])
        np.testing.assert_array_equal(y, [2, 3, 4, 5])

    def test_roundtrip_preserves_scale(self) -> None:
        c = FigureCurve("A", np.arange(4.0), np.arange(4.0), x_scale=1e-6, y_scale=100.0)
        with tempfile.TemporaryDirectory() as d:
            back = load_figure(save_figure(FigureDoc(curves=[c]), Path(d) / "f"))
        self.assertEqual(back.curves[0].x_scale, 1e-6)
        self.assertEqual(back.curves[0].y_scale, 100.0)

    def test_load_legacy_without_scale_defaults_to_one(self) -> None:
        import json
        from dataclasses import asdict

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "legacy.npz"
            meta = {
                "x_label": "x", "y_label": "y", "x_format": "%g", "y_format": "%g",
                "title": "", "x_limits": None, "y_limits": None,
                "curves": [{"name": "A", "style": asdict(CurveStyle()),
                            "x_lo": None, "x_hi": None}],  # pre-scale schema
            }
            np.savez(p, c0_x=np.arange(3.0), c0_y=np.arange(3.0),
                     meta=np.asarray(json.dumps(meta)))
            back = load_figure(p)
        self.assertEqual(back.curves[0].x_scale, 1.0)
        self.assertEqual(back.curves[0].y_scale, 1.0)
        # publication-export settings absent from old files default sensibly
        self.assertEqual(back.style, "default")
        self.assertFalse(back.use_latex)
        self.assertEqual((back.fig_width, back.fig_height), (6.4, 4.8))
        self.assertEqual(back.label_fontsize, 14.0)


if __name__ == "__main__":
    unittest.main()
