"""I/O and small numeric helpers that mirror the legacy MATLAB behaviour.

The MATLAB code reads/writes plain-text matrices via `load`/`save -ascii`, indexes from
1, and rounds half-away-from-zero. These helpers reproduce those conventions so the Python
port lines up with the `gold/` fixtures.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np


def mround(x: np.ndarray | float) -> np.ndarray | int:
    """MATLAB `round`: round half away from zero (numpy rounds half to even)."""
    rounded = np.sign(x) * np.floor(np.abs(x) + 0.5)
    if np.isscalar(x):
        return int(rounded)
    return rounded.astype(int)


def load_signal(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    """Load a 2-column ``[value, time]`` signal (FLT export or `.inc`/`.tra`).

    Skips any non-numeric header lines (the FLT source-name + units lines, or the leading
    blank line of a MATLAB-saved `.inc`/`.tra`).
    """
    values: list[float] = []
    times: list[float] = []
    for line in Path(path).read_text(errors="replace").splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        try:
            v, t = float(parts[0]), float(parts[1])
        except ValueError:
            continue  # header line
        values.append(v)
        times.append(t)
    return np.asarray(values, dtype=float), np.asarray(times, dtype=float)


def sampling_interval(times: np.ndarray) -> float:
    """Sampling interval ``tpp`` (s) recovered from a signal's time column.

    The median sample-to-sample step — robust to the tiny float jitter in the recorded time
    axis and to the occasional duplicated/dropped sample. ``tpp`` is a property of the capture,
    not an operator choice, so the pipeline reads it from here rather than from any config file.
    """
    t = np.asarray(times, dtype=float).ravel()
    if t.size < 2:
        raise ValueError("need >= 2 time samples to derive the sampling interval (tpp)")
    dt = float(np.median(np.diff(t)))
    if not dt > 0.0:
        raise ValueError(f"non-positive sampling interval derived from the time column: {dt!r}")
    return dt


def load_matrix(path: str | Path) -> np.ndarray:
    """Load a whitespace-delimited numeric matrix, ignoring `%`/`#` comments."""
    return np.loadtxt(path, comments=["%", "#"])


def _format_value(x: float) -> str:
    """Format one number the way MATLAB `save -ascii` does (8 sig figs, 3-digit exp)."""
    mantissa, exponent = f"{x: .7e}".split("e")
    sign, digits = exponent[0], exponent[1:]
    return f"{mantissa}e{sign}{int(digits):03d}"


def save_ascii(path: str | Path, arr: np.ndarray) -> None:
    """Write ``arr`` like MATLAB `save <name> <var> -ascii`.

    A 1-D array is written one value per line (MATLAB column-vector layout). For
    byte-faithfulness MATLAB would emit a row vector on one line, but the port keeps the
    numerically-meaningful column layout; gold comparisons are numeric, not byte-exact.
    """
    arr = np.asarray(arr, dtype=float)
    rows = arr.reshape(-1, 1) if arr.ndim == 1 else arr
    with Path(path).open("w", encoding="ascii") as f:
        for row in rows:
            f.write("  " + "  ".join(_format_value(v) for v in row) + "\n")
