"""Regression tests for the twobar backend against the MATLAB ``gold/`` fixtures.

The analysis stage is validated by *numeric tolerance* (not byte-equality like the WFT
converter): FFT/filter math and float formatting will not be bit-identical to MATLAB.

The two operator choices the GUI used for this fixture are passed explicitly:
  * ``tim_cut``  — read from ``gold/tim_cut`` (the pulse-start click).
  * ``reflect_shift = 3`` — the reflected-pulse slider shift, recovered from the gold
    mechanics (``f_in``/``v_in2`` only line up with this shift; MSE vs gold ~1e-21).
"""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np

from hopki import twobar

ROOT = Path(__file__).resolve().parent
GOLD = ROOT / "gold"
REFLECT_SHIFT = 3


def gold(name: str) -> np.ndarray:
    return np.loadtxt(GOLD / name)


class TwobarGoldTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inc, tra, exp, spec, damp_f = twobar.load_inputs(ROOT)
        cls.exp, cls.spec = exp, spec
        cls.tim_cut = float(gold("tim_cut"))
        cls.result = twobar.run_analysis(
            inc, tra, exp, spec, damp_f,
            tim_cut=cls.tim_cut, reflect_shift=REFLECT_SHIFT, invert_signals=True,
        )

    def assert_close(self, actual: np.ndarray, expected: np.ndarray, *, rtol: float, atol: float) -> None:
        actual = np.asarray(actual).ravel()
        expected = np.asarray(expected).ravel()
        self.assertEqual(actual.shape, expected.shape)
        max_abs = float(np.max(np.abs(actual - expected)))
        scale = max(float(np.max(np.abs(expected))), 1.0)
        self.assertTrue(
            np.allclose(actual, expected, rtol=rtol, atol=atol),
            msg=f"max|Δ|={max_abs:.3e} (scale={scale:.3e}, rel={max_abs/scale:.3e})",
        )

    # ---- stage 1: windowing ------------------------------------------------
    def test_inc_puls(self) -> None:
        self.assert_close(self.result.windowed.incident, gold("inc_puls"), rtol=0, atol=1e-9)

    def test_ref_puls(self) -> None:
        self.assert_close(self.result.windowed.reflected, gold("ref_puls"), rtol=0, atol=1e-9)

    def test_tra_puls(self) -> None:
        self.assert_close(self.result.windowed.transmitted, gold("tra_puls"), rtol=0, atol=1e-9)

    # ---- stage 2: dispersion correction ------------------------------------
    def test_inc_corr(self) -> None:
        self.assert_close(self.result.corrected.incident, gold("inc_corr"), rtol=1e-5, atol=1e-9)

    def test_ref_corr(self) -> None:
        self.assert_close(self.result.corrected.reflected, gold("ref_corr"), rtol=1e-5, atol=1e-9)

    def test_tra_corr(self) -> None:
        self.assert_close(self.result.corrected.transmitted, gold("tra_corr"), rtol=1e-5, atol=1e-9)

    # ---- stage 4: mechanics (value column of each [time, value] gold file) -
    def test_v_striker(self) -> None:
        self.assert_close(self.result.mechanics.v_striker, gold("v_striker"), rtol=1e-5, atol=1e-6)

    def test_v_in2(self) -> None:
        self.assert_close(self.result.mechanics.v_in, gold("v_in2"), rtol=1e-5, atol=1e-6)

    def test_f_in(self) -> None:
        self.assert_close(self.result.mechanics.f_in, gold("f_in")[:, 1], rtol=1e-4, atol=1e-3)

    def test_f_out(self) -> None:
        self.assert_close(self.result.mechanics.f_out, gold("f_out")[:, 1], rtol=1e-5, atol=1e-3)

    def test_v_in(self) -> None:
        self.assert_close(self.result.mechanics.v_in, gold("v_in")[:, 1], rtol=1e-5, atol=1e-6)

    def test_v_out(self) -> None:
        self.assert_close(self.result.mechanics.v_out, gold("v_out")[:, 1], rtol=1e-5, atol=1e-6)

    def test_u_in(self) -> None:
        self.assert_close(self.result.mechanics.u_in, gold("u_in")[:, 1], rtol=1e-5, atol=1e-9)

    def test_u_out(self) -> None:
        self.assert_close(self.result.mechanics.u_out, gold("u_out")[:, 1], rtol=1e-5, atol=1e-9)

    def test_e_dot(self) -> None:
        self.assert_close(self.result.mechanics.eps_rate_eng, gold("e_dot")[:, 1], rtol=1e-5, atol=1e-6)

    def test_s_e_eng(self) -> None:
        g = gold("s_e_eng")
        self.assert_close(self.result.mechanics.eps_eng, g[:, 0], rtol=1e-5, atol=1e-7)
        self.assert_close(self.result.mechanics.str_eng, g[:, 1], rtol=1e-4, atol=1e-1)

    def test_s_e_true(self) -> None:
        g = gold("s_e_true")
        self.assert_close(self.result.mechanics.eps_true, g[:, 0], rtol=1e-5, atol=1e-7)
        self.assert_close(self.result.mechanics.str_true, g[:, 1], rtol=1e-4, atol=1e-1)

    # ---- time base ---------------------------------------------------------
    def test_time_base(self) -> None:
        self.assert_close(self.result.mechanics.time, gold("f_in")[:, 0], rtol=0, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
