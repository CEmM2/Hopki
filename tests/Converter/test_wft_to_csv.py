from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from hopki.wft_to_csv import convert_one, read_wft


ROOT = Path(__file__).resolve().parent
EXPECTED = ROOT / "gold"


def parse_flt(path: Path) -> tuple[list[float], list[float]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    data_lines = [line for line in lines[2:] if line.strip()]
    values: list[float] = []
    times: list[float] = []
    for line in data_lines:
        value_text, time_text = line.split()
        values.append(float(value_text))
        times.append(float(time_text))
    return values, times


class WftConversionRegressionTests(unittest.TestCase):
    def assert_matches_reference(self, stem: str) -> None:
        expected_values, expected_times = parse_flt(EXPECTED / f"{stem}.FLT")
        wft = read_wft(ROOT / f"{stem}.WFT")

        self.assertEqual(len(wft.value), len(expected_values))
        self.assertEqual(len(wft.time), len(expected_times))

        for idx, (actual, expected) in enumerate(zip(wft.value, expected_values, strict=True)):
            self.assertAlmostEqual(actual, expected, places=12, msg=f"value mismatch at sample {idx}")

        for idx, (actual, expected) in enumerate(zip(wft.time, expected_times, strict=True)):
            self.assertAlmostEqual(actual, expected, places=12, msg=f"time mismatch at sample {idx}")

    def test_wave0003_matches_reference_export(self) -> None:
        self.assert_matches_reference("WAVE0003")

    def test_wave0004_matches_reference_export(self) -> None:
        self.assert_matches_reference("WAVE0004")

    def test_wave0003_written_output_matches_reference_export(self) -> None:
        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "WAVE0003.FLT"
            convert_one(ROOT / "WAVE0003.WFT", out_path, meta=False)
            actual_lines = out_path.read_text(encoding="utf-8").splitlines()
            expected_lines = (EXPECTED / "WAVE0003.FLT").read_text(encoding="utf-8").splitlines()
            self.assertEqual(actual_lines, expected_lines)

    def test_wave0004_written_output_matches_reference_export(self) -> None:
        with TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "WAVE0004.FLT"
            convert_one(ROOT / "WAVE0004.WFT", out_path, meta=False)
            actual_lines = out_path.read_text(encoding="utf-8").splitlines()
            expected_lines = (EXPECTED / "WAVE0004.FLT").read_text(encoding="utf-8").splitlines()
            self.assertEqual(actual_lines, expected_lines)


if __name__ == "__main__":
    unittest.main()