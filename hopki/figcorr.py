"""Port of ``fig_corr.m`` — stress-strain curve cleanup tools (GUI-free).

``fig_corr.m`` post-processes one saved curve (e.g. ``s_e_true``) through a set of
interactive operations. Here each operation is a pure function on a :class:`Curve`, with the
GUI's ``ginput`` picks turned into explicit arguments — same "option (a)" design as the
analysis backend, so a sequence of edits is reproducible and scriptable.

The operations, mapped to their MATLAB callbacks:
    zero        <- zero_button       (translate curve to the origin)
    cut         <- cut_pushbutton    (keep the first N samples)
    crop_start  <- shift_pushbutton  (drop the first N-1 samples)
    smooth      <- filt_button       (zero-phase Butterworth low-pass on stress)
    straighten  <- straight          (toe / foot correction)
    slope       <- slope_Callback    (modulus readout between two points)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .matlab_io import load_matrix, mround, save_ascii
from .trans2nic import butter_filter


@dataclass
class Curve:
    """A stress-strain curve: ``e`` is the x channel (strain), ``s`` the y channel (stress)."""

    e: np.ndarray
    s: np.ndarray


def load_curve(path: str | Path) -> Curve:
    """Load a curve file (``fig_corr`` ``ok_button``).

    A 2-column file is read as ``[strain, stress]``. A single-column file is treated as
    stress vs. its 1-based sample index (matching the MATLAB single-column branch).
    """
    data = np.atleast_2d(load_matrix(path))
    if data.shape[0] == 1 and data.shape[1] > 1:
        data = data.T  # a row-vector file is a single column of values
    if data.shape[1] == 1:
        s = data[:, 0].astype(float)
        e = np.arange(1, len(s) + 1, dtype=float)
    else:
        e, s = data[:, 0].astype(float), data[:, 1].astype(float)
    return Curve(e, s)


def save_curve(curve: Curve, path: str | Path) -> None:
    """Write the curve as a 2-column ``[strain, stress]`` ``-ascii`` file (``save_Callback``)."""
    save_ascii(path, np.column_stack([curve.e, curve.s]))


def zero(curve: Curve) -> Curve:
    """``zero_button``: translate both channels so the first sample is at the origin."""
    return Curve(curve.e - curve.e[0], curve.s - curve.s[0])


def cut(curve: Curve, end_index: float) -> Curve:
    """``cut_pushbutton``: keep the first ``end_index`` samples (1-based, as clicked)."""
    n = mround(end_index)
    return Curve(curve.e[:n].copy(), curve.s[:n].copy())


def crop_start(curve: Curve, start_index: float) -> Curve:
    """``shift_pushbutton``: keep samples from ``start_index`` onward (1-based)."""
    i = mround(start_index) - 1
    return Curve(curve.e[i:].copy(), curve.s[i:].copy())


def smooth(curve: Curve, cutoff: float, order: int = 4) -> Curve:
    """``filt_button``: zero-phase Butterworth low-pass on the stress channel.

    ``cutoff`` is a normalized frequency in (0, 1), the value clicked off the PSD in the GUI.
    """
    return Curve(curve.e.copy(), butter_filter(curve.s, cutoff, order=order))


def power_spectrum(y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Magnitude spectrum of ``y`` vs **normalized frequency** (1 == Nyquist).

    The frequency axis is scaled to match ``butter_filter``'s ``cutoff`` convention (0..1,
    where 1 is Nyquist), so a frequency read off this spectrum is exactly the ``cutoff`` to
    pass to :func:`smooth`. The DC component is removed first so the low-frequency bins reflect
    signal/noise structure rather than the (usually large) mean offset.
    """
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 2:
        return np.zeros(0), np.zeros(0)
    freq = np.fft.rfftfreq(n) * 2.0  # rfftfreq is cycles/sample in [0, 0.5]; *2 -> Nyquist == 1
    mag = np.abs(np.fft.rfft(y - y.mean()))
    return freq, mag


def straighten(curve: Curve, p1: tuple[float, float], p2: tuple[float, float]) -> Curve:
    """``straight``: toe (foot) correction.

    ``p1`` and ``p2`` are two points on the linear loading region. The line through them is
    extrapolated to zero stress (x-intercept ``x_new``); samples with strain below ``p1``'s x
    are dropped, and the first remaining sample is moved to ``(x_new, 0)``.
    """
    (x1, y1), (x2, y2) = p1, p2
    x_new = x1 - y1 * (x2 - x1) / (y2 - y1)
    hits = np.flatnonzero(curve.e >= x1)
    i = int(hits[0]) if hits.size else 0
    e = curve.e[i:].copy()
    s = curve.s[i:].copy()
    s[0] = 0.0
    e[0] = x_new
    return Curve(e, s)


def slope(p1: tuple[float, float], p2: tuple[float, float]) -> float:
    """``slope_Callback``: modulus (slope) between two clicked points."""
    (x1, y1), (x2, y2) = p1, p2
    return (y2 - y1) / (x2 - x1)


def negate(curve: Curve, axis: str = "stress") -> Curve:
    """Flip the sign of the stress and/or strain channel.

    ``axis`` is ``"stress"``, ``"strain"``, or ``"both"`` — handy when a curve comes out
    mirrored (e.g. a polarity/convention mismatch in the source signals).
    """
    if axis not in ("stress", "strain", "both"):
        raise ValueError(f"axis must be 'stress', 'strain', or 'both', got {axis!r}")
    e = -curve.e if axis in ("strain", "both") else curve.e.copy()
    s = -curve.s if axis in ("stress", "both") else curve.s.copy()
    return Curve(e, s)


def scale(curve: Curve, axis: str, factor: float) -> Curve:
    """Multiply one axis by a constant (``axis`` is "stress" or "strain")."""
    if axis == "stress":
        return Curve(curve.e.copy(), curve.s * factor)
    return Curve(curve.e * factor, curve.s.copy())


def shift(curve: Curve, axis: str, delta: float) -> Curve:
    """Translate one axis by a constant (``axis`` is "stress" or "strain").

    Unlike :func:`zero` (which moves the *first sample* of both channels to the origin), this
    offsets a single chosen axis by an explicit amount.
    """
    if axis == "stress":
        return Curve(curve.e.copy(), curve.s + delta)
    return Curve(curve.e + delta, curve.s.copy())


def to_true(curve: Curve) -> Curve:
    """Convert an **engineering** σ–ε curve to true stress / true strain.

    Mirrors ``twobar.compute_mechanics`` (and the bundled-gold convention): with ``eps`` the
    engineering strain (``curve.e``) and ``sigma`` the engineering stress (``curve.s``)::

        eps_true   = -log(1 - eps)        # = -log(1 + e), with e = -eps
        sigma_true =  sigma * (1 + eps)   # = sigma * (1 - e)

    True stress/strain are *nonlinear* in engineering strain, so a true curve must be derived
    from the engineering one — scaling a true axis directly is wrong. Apply only to engineering
    data (the cleanup tab disables this for a curve pulled as true σ–ε). The asymmetric signs
    are the documented gold convention (see ``compute_mechanics``); strain at or beyond
    ``eps = 1`` drives ``1 - eps`` non-positive and yields non-finite true strain.
    """
    e = -np.asarray(curve.e, dtype=float)
    eps_true = -np.log(1.0 + e)
    str_true = np.asarray(curve.s, dtype=float) * (1.0 - e)
    return Curve(eps_true, str_true)


def main(argv: list[str] | None = None) -> int:
    """CLI: apply a fixed-order sequence of cleanup ops to a curve and save ``<name>_corr``.

    Operations are applied in the order: crop-start -> cut -> straighten -> smooth -> zero
    (only those requested). Indices/points are chosen by inspecting the curve beforehand.
    """
    p = argparse.ArgumentParser(description="Clean up a stress-strain curve (fig_corr port).")
    p.add_argument("input", type=Path, help="curve file to load (1- or 2-column)")
    p.add_argument("--crop-start", type=float, metavar="N", help="keep samples from index N")
    p.add_argument("--cut", type=float, metavar="N", help="keep the first N samples")
    p.add_argument("--straighten", type=float, nargs=4, metavar=("X1", "Y1", "X2", "Y2"),
                   help="toe correction from two points on the linear region")
    p.add_argument("--smooth", type=float, metavar="CUTOFF",
                   help="Butterworth low-pass at normalized cutoff in (0, 1)")
    p.add_argument("--zero", action="store_true", help="translate the curve to the origin")
    p.add_argument("--out", type=Path, default=None,
                   help="output path (default: <input>_corr)")
    args = p.parse_args(argv)

    curve = load_curve(args.input)
    if args.crop_start is not None:
        curve = crop_start(curve, args.crop_start)
    if args.cut is not None:
        curve = cut(curve, args.cut)
    if args.straighten is not None:
        x1, y1, x2, y2 = args.straighten
        curve = straighten(curve, (x1, y1), (x2, y2))
    if args.smooth is not None:
        curve = smooth(curve, args.smooth)
    if args.zero:
        curve = zero(curve)

    out = args.out or args.input.with_name(f"{args.input.name}_corr")
    save_curve(curve, out)
    print(f"wrote {out} ({len(curve.e)} points)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
