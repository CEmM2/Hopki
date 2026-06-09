"""Round-trip tests for the MATLAB-style ``save_ascii`` writer and ``write_results``.

``save_ascii`` emits 8-significant-figure text, so a write -> read cycle should recover the
values to ~1e-7 relative. These tests guard the writer/reader pair and the CLI output set.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from hopki import twobar
from hopki.matlab_io import load_matrix, save_ascii

ROOT = Path(__file__).resolve().parent


class SaveAsciiRoundTripTests(unittest.TestCase):
    def test_scalar_vector_matrix(self) -> None:
        rng = np.random.default_rng(0)
        cases = [
            np.array([3.14159265358979]),
            rng.standard_normal(64) * 1e7,
            rng.standard_normal((40, 2)) * 1e-4,
            np.array([0.0, -1.0e-12, 2.5e11]),
        ]
        for arr in cases:
            with tempfile.TemporaryDirectory() as d:
                path = Path(d) / "x"
                save_ascii(path, arr)
                back = load_matrix(path).reshape(arr.shape)
                np.testing.assert_allclose(back, arr, rtol=1e-7, atol=1e-15)


class WriteResultsRoundTripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inc, tra, exp, spec, damp_f = twobar.load_inputs(ROOT)
        cls.exp = exp
        cls.tim_cut = float(np.loadtxt(ROOT / "gold" / "tim_cut"))
        cls.result = twobar.run_analysis(
            inc, tra, exp, spec, damp_f,
            tim_cut=cls.tim_cut, reflect_shift=3, invert_signals=True,
        )

    def test_written_files_match_in_memory(self) -> None:
        m = self.result.mechanics
        with tempfile.TemporaryDirectory() as d:
            written = twobar.write_results(self.result, self.exp, d, tim_cut=self.tim_cut)
            names = {p.name for p in written}
            for required in ("inc_corr", "f_in", "s_e_true", "v_in2", "tpp", "tim_cut"):
                self.assertIn(required, names)

            np.testing.assert_allclose(
                load_matrix(Path(d) / "inc_corr").ravel(), self.result.corrected.incident,
                rtol=1e-6, atol=1e-9)
            np.testing.assert_allclose(
                load_matrix(Path(d) / "f_in")[:, 1], m.f_in, rtol=1e-6, atol=1e-2)
            np.testing.assert_allclose(
                load_matrix(Path(d) / "f_in")[:, 0], m.time, rtol=0, atol=1e-12)
            se = load_matrix(Path(d) / "s_e_true")
            np.testing.assert_allclose(se[:, 0], m.eps_true, rtol=1e-6, atol=1e-7)
            np.testing.assert_allclose(se[:, 1], m.str_true, rtol=1e-6, atol=1e-1)
            np.testing.assert_allclose(
                load_matrix(Path(d) / "v_in2").ravel(), m.v_in, rtol=1e-6, atol=1e-6)

    def test_cli_writes_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            rc = twobar.main([
                str(ROOT), "--tim-cut", repr(self.tim_cut),
                "--reflect-shift", "3", "--invert", "--out", d,
            ])
            self.assertEqual(rc, 0)
            self.assertTrue((Path(d) / "s_e_eng").exists())
            # CLI result should reproduce gold (same params as the gold run).
            f_in = load_matrix(Path(d) / "f_in")[:, 1]
            gold_f_in = np.loadtxt(ROOT / "gold" / "f_in")[:, 1]
            np.testing.assert_allclose(f_in, gold_f_in, rtol=1e-4, atol=1e-2)


if __name__ == "__main__":
    unittest.main()
