"""Port of ``trans2nic_g.m`` — split a recorded experiment into Nicolet `.inc`/`.tra`.

The MATLAB tool takes a 3-column ``[time, incident, transmitted]`` capture, splits it into
``incid = [incident, time]`` and ``trans = [transmitted, time]``, optionally runs an adaptive
Butterworth filter on each channel, and saves ``incid.inc`` / ``trans.tra``.

Two faithfulness notes:
  * The original ``filt_adap1`` loops ``filtfilt`` 7x but recomputes from the raw signal each
    pass, so the loop is a no-op — the effective filter is a single ``filtfilt``. We default
    ``passes=1`` to match that effective behaviour (override if you actually want cascading).
  * The cutoff is interactive in the GUI (clicked off a Welch PSD plot). Here it is the
    ``cutoff`` argument, a normalized frequency in (0, 1) as ``scipy.signal.butter`` expects.
    Pass ``cutoff=None`` to skip filtering (reproduces the raw split, as in the gold fixtures).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.signal import butter, filtfilt

from .matlab_io import load_matrix, save_ascii


def butter_filter(signal: np.ndarray, cutoff: float, order: int = 4, passes: int = 1) -> np.ndarray:
    """Zero-phase Butterworth low-pass (``scipy`` ``butter`` + ``filtfilt``).

    ``cutoff`` is a normalized frequency in (0, 1) (1 == Nyquist), matching MATLAB
    ``butter(order, Wn)``.
    """
    b, a = butter(order, cutoff)
    out = np.asarray(signal, dtype=float)
    for _ in range(passes):
        out = filtfilt(b, a, out)
    return out


@dataclass
class NicoletSignals:
    """``incid``/``trans`` as ``[value, time]`` 2-column arrays (MATLAB save layout)."""

    incid: np.ndarray
    trans: np.ndarray


def split(
    time: np.ndarray,
    incident: np.ndarray,
    transmitted: np.ndarray,
    cutoff: float | None = None,
    *,
    order: int = 4,
    passes: int = 1,
) -> NicoletSignals:
    """Split (and optionally filter) into Nicolet ``[value, time]`` channels."""
    time = np.asarray(time, dtype=float)
    inc = np.asarray(incident, dtype=float)
    tra = np.asarray(transmitted, dtype=float)
    if cutoff is not None:
        inc = butter_filter(inc, cutoff, order=order, passes=passes)
        tra = butter_filter(tra, cutoff, order=order, passes=passes)
    return NicoletSignals(
        incid=np.column_stack([inc, time]),
        trans=np.column_stack([tra, time]),
    )


def convert_file(
    path: str | Path,
    out_dir: str | Path | None = None,
    cutoff: float | None = None,
) -> NicoletSignals:
    """Read a 3-column ``[time, incident, transmitted]`` capture and write `.inc`/`.tra`."""
    data = load_matrix(path)
    signals = split(data[:, 0], data[:, 1], data[:, 2], cutoff=cutoff)
    out = Path(out_dir) if out_dir else Path(path).parent
    save_ascii(out / "incid.inc", signals.incid)
    save_ascii(out / "trans.tra", signals.trans)
    return signals
