"""Unit tests for the fig_corr curve-cleanup port (pure transforms + I/O)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from hopki import figcorr
from hopki.figcorr import Curve


class CurveOpsTests(unittest.TestCase):
    def make(self) -> Curve:
        e = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        s = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
        return Curve(e, s)

    def test_zero(self) -> None:
        c = figcorr.zero(self.make())
        self.assertEqual(c.e[0], 0.0)
        self.assertEqual(c.s[0], 0.0)
        np.testing.assert_allclose(c.s, [0, 1, 2, 3, 4])

    def test_cut_keeps_first_n(self) -> None:
        c = figcorr.cut(self.make(), 3)
        np.testing.assert_allclose(c.e, [0, 1, 2])
        np.testing.assert_allclose(c.s, [10, 11, 12])

    def test_crop_start_drops_leading(self) -> None:
        c = figcorr.crop_start(self.make(), 3)  # 1-based -> drop first two
        np.testing.assert_allclose(c.e, [2, 3, 4])
        np.testing.assert_allclose(c.s, [12, 13, 14])

    def test_straighten_toe_correction(self) -> None:
        # Line s = e through the origin; pick two points on it.
        e = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        c = Curve(e, e.copy())
        out = figcorr.straighten(c, (2.0, 2.0), (4.0, 4.0))
        # x-intercept of the (2,2)-(4,4) line is 0; keep from first e>=2 (index 2).
        np.testing.assert_allclose(out.e, [0.0, 3.0, 4.0])  # first strain reset to x_new=0
        np.testing.assert_allclose(out.s, [0.0, 3.0, 4.0])  # first stress reset to 0

    def test_straighten_nonzero_intercept(self) -> None:
        e = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        c = Curve(e, e.copy())
        out = figcorr.straighten(c, (2.0, 1.0), (4.0, 3.0))  # slope 1, x-intercept = 1
        self.assertAlmostEqual(out.e[0], 1.0)
        self.assertEqual(out.s[0], 0.0)

    def test_smooth_preserves_length_and_strain(self) -> None:
        rng = np.random.default_rng(1)
        e = np.linspace(0, 1, 200)
        s = np.sin(2 * np.pi * 3 * e) + 0.3 * rng.standard_normal(200)
        out = figcorr.smooth(Curve(e, s), 0.1)
        self.assertEqual(len(out.s), len(s))
        np.testing.assert_array_equal(out.e, e)
        self.assertLess(out.s.var(), s.var())

    def test_power_spectrum_peaks_at_signal_frequency(self) -> None:
        # A pure tone at k cycles over n samples peaks at normalized freq 2k/n (Nyquist == 1).
        n, k = 256, 8
        e = np.arange(n, dtype=float)
        s = np.sin(2 * np.pi * k * e / n)
        freq, mag = figcorr.power_spectrum(s)
        self.assertEqual(freq.shape, mag.shape)
        self.assertAlmostEqual(freq[0], 0.0)
        self.assertAlmostEqual(freq[-1], 1.0, places=6)  # last bin is Nyquist
        self.assertAlmostEqual(float(freq[np.argmax(mag)]), 2 * k / n, places=6)

    def test_power_spectrum_handles_short_input(self) -> None:
        freq, mag = figcorr.power_spectrum(np.array([1.0]))
        self.assertEqual(freq.size, 0)
        self.assertEqual(mag.size, 0)

    def test_slope(self) -> None:
        self.assertAlmostEqual(figcorr.slope((1.0, 2.0), (3.0, 8.0)), 3.0)

    def test_negate(self) -> None:
        c = Curve(np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0]))
        s = figcorr.negate(c, "stress")
        np.testing.assert_allclose(s.e, [1, 2, 3])
        np.testing.assert_allclose(s.s, [-4, -5, -6])
        e = figcorr.negate(c, "strain")
        np.testing.assert_allclose(e.e, [-1, -2, -3])
        np.testing.assert_allclose(e.s, [4, 5, 6])
        b = figcorr.negate(c, "both")
        np.testing.assert_allclose(b.e, [-1, -2, -3])
        np.testing.assert_allclose(b.s, [-4, -5, -6])
        with self.assertRaises(ValueError):
            figcorr.negate(c, "nope")

    def test_scale(self) -> None:
        c = Curve(np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0]))
        s = figcorr.scale(c, "stress", 1e-6)
        np.testing.assert_allclose(s.e, [1, 2, 3])           # strain untouched
        np.testing.assert_allclose(s.s, [4e-6, 5e-6, 6e-6])
        e = figcorr.scale(c, "strain", 100.0)
        np.testing.assert_allclose(e.e, [100, 200, 300])
        np.testing.assert_allclose(e.s, [4, 5, 6])           # stress untouched
        # original curve is not mutated
        np.testing.assert_allclose(c.e, [1, 2, 3])
        np.testing.assert_allclose(c.s, [4, 5, 6])

    def test_shift(self) -> None:
        c = Curve(np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0, 6.0]))
        s = figcorr.shift(c, "stress", -10.0)
        np.testing.assert_allclose(s.e, [1, 2, 3])           # strain untouched
        np.testing.assert_allclose(s.s, [-6, -5, -4])
        e = figcorr.shift(c, "strain", 0.5)
        np.testing.assert_allclose(e.e, [1.5, 2.5, 3.5])
        np.testing.assert_allclose(e.s, [4, 5, 6])           # stress untouched
        # original curve is not mutated
        np.testing.assert_allclose(c.e, [1, 2, 3])
        np.testing.assert_allclose(c.s, [4, 5, 6])

    def test_to_true(self) -> None:
        # eps_true = -log(1 - eps), sigma_true = sigma * (1 + eps)
        c = Curve(np.array([0.0, 0.1, 0.2]), np.array([0.0, 100.0, 200.0]))
        t = figcorr.to_true(c)
        np.testing.assert_allclose(t.e, [0.0, -np.log(0.9), -np.log(0.8)])
        np.testing.assert_allclose(t.s, [0.0, 110.0, 240.0])
        # original is not mutated
        np.testing.assert_allclose(c.e, [0.0, 0.1, 0.2])


class CurveIoTests(unittest.TestCase):
    def test_save_load_roundtrip(self) -> None:
        e = np.linspace(0, 0.3, 50)
        s = 2.0e8 * e
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s_e_true"
            figcorr.save_curve(Curve(e, s), path)
            back = figcorr.load_curve(path)
            np.testing.assert_allclose(back.e, e, rtol=1e-6, atol=1e-9)
            np.testing.assert_allclose(back.s, s, rtol=1e-6, atol=1e-1)

    def test_load_single_column_uses_index(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "col"
            from hopki.matlab_io import save_ascii
            save_ascii(path, np.array([5.0, 6.0, 7.0]))
            c = figcorr.load_curve(path)
            np.testing.assert_allclose(c.e, [1, 2, 3])  # 1-based index
            np.testing.assert_allclose(c.s, [5, 6, 7])


if __name__ == "__main__":
    unittest.main()
