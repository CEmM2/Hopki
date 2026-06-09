"""Tests for signal-derived tpp and the x1/x2 auto-estimation.

The bundled fixture's known geometry is x1=0.558 m, x2=0.230 m, tpp=0.5e-6 s. x1 is recovered
robustly from the reflected pulse; x2 is best-effort (the transmitted pulse is weak/reshaped),
so it is only asserted to be positive and plausibly bounded, not accurate.
"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np

from hopki import config, twobar
from hopki.geometry import estimate_distances
from hopki.matlab_io import load_signal, sampling_interval

ROOT = Path(__file__).resolve().parent


class SamplingIntervalTests(unittest.TestCase):
    def test_recovers_tpp_from_fixture(self) -> None:
        _, t = load_signal(ROOT / "WAVE0030.FLT")
        self.assertAlmostEqual(sampling_interval(t), 0.5e-6, places=12)

    def test_robust_to_jitter_and_uses_median(self) -> None:
        t = np.arange(100) * 2e-6
        t[50] += 1e-9  # a single jittered sample must not move the median step
        self.assertAlmostEqual(sampling_interval(t), 2e-6, places=12)

    def test_rejects_degenerate_input(self) -> None:
        with self.assertRaises(ValueError):
            sampling_interval(np.array([0.0]))
        with self.assertRaises(ValueError):
            sampling_interval(np.array([0.0, 0.0, 0.0]))


class EstimateDistancesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.inc, _ = load_signal(ROOT / "WAVE0030.FLT")
        cls.tra, _ = load_signal(ROOT / "WAVE0031.FLT")

    def _estimate(self):
        return estimate_distances(
            self.inc, self.tra, c0=4800.0, tpp=0.5e-6, npoint=450, nlong=1000,
        )

    def test_x1_recovered_accurately(self) -> None:
        est = self._estimate()
        self.assertAlmostEqual(est.x1, 0.558, delta=0.01)  # ~2% — robust reflected-pulse match
        self.assertGreater(est.x1_corr, 0.7)               # clean lock

    def test_x2_best_effort_positive(self) -> None:
        est = self._estimate()
        self.assertGreater(est.x2, 0.0)
        self.assertLess(est.x2, 1.0)        # same order as the true 0.230, not wild
        self.assertGreater(est.x2_snr, 1.0)  # transmitted pulse clears the noise floor

    def test_polarity_invariant(self) -> None:
        flipped = estimate_distances(
            -self.inc, -self.tra, c0=4800.0, tpp=0.5e-6, npoint=450, nlong=1000,
        )
        self.assertAlmostEqual(flipped.x1, self._estimate().x1, places=9)


class LoadInputsEstimationTests(unittest.TestCase):
    def _toml_dir(self, body: str) -> Path:
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, ignore_errors=True)
        for name in ("WAVE0030.FLT", "WAVE0031.FLT"):
            shutil.copy(ROOT / name, d / name)
        (d / "hopki.toml").write_text(body)
        return d

    def test_legacy_fixture_does_not_estimate(self) -> None:
        # The gold fixture is legacy (positional incid.exp) -> all bar keys present, no estimate.
        present = config.present_bar_keys(ROOT)
        self.assertIn("x1", present)
        self.assertIn("x2", present)
        _, _, exp, _, _ = twobar.load_inputs(ROOT)
        self.assertEqual(exp.x1, 0.558)   # untouched, straight from incid.exp
        self.assertEqual(exp.x2, 0.230)

    def test_toml_without_distances_triggers_estimation(self) -> None:
        d = self._toml_dir(
            "[bar]\nnlong = 1000\nnpoint = 450\nc0 = 4800\n"
            'diam_bar = 1.27e-2\nE = 1.9e11\ngfact = 2.13\nvbridge = 10.15\n'
        )
        present = config.present_bar_keys(d)
        self.assertNotIn("x1", present)
        self.assertNotIn("x2", present)
        _, _, exp, _, _ = twobar.load_inputs(d)
        self.assertAlmostEqual(exp.x1, 0.558, delta=0.01)  # auto-estimated
        self.assertGreater(exp.x2, 0.0)
        self.assertAlmostEqual(exp.tpp, 0.5e-6, places=12)  # derived from the signal

    def test_configured_x1_is_kept_x2_estimated(self) -> None:
        # x1 given explicitly, x2 omitted -> x1 honored exactly, only x2 estimated.
        d = self._toml_dir("[bar]\nc0 = 4800\nx1 = 0.42\n")
        _, _, exp, _, _ = twobar.load_inputs(d)
        self.assertEqual(exp.x1, 0.42)
        self.assertGreater(exp.x2, 0.0)


if __name__ == "__main__":
    unittest.main()
