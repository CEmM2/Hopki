"""Auto-estimate the gauge-to-specimen distances ``x1``/``x2`` from the raw signals.

When an experiment's ``hopki.toml`` omits ``x1``/``x2`` (someone forgot to measure them, or
the lab setup notes are lost), the analysis still needs them to window the reflected pulse
(returns to gauge 1 after ``2*x1/c0``) and the transmitted pulse (reaches gauge 2 after
``(x1+x2)/c0``). Both delays are visible in the signals, so the distances can be recovered:

* **x1 is robust.** The reflected pulse is a near-copy of the incident pulse (same shape, just
  inverted and dispersed), so a normalized matched filter of the incident window against the
  rest of the incident-bar channel locks onto the reflected return cleanly. And because x1
  comes from the *difference* of two lags in the same channel, it is immune to exactly where
  the incident pulse is judged to start.

* **x2 is best-effort only.** The transmitted pulse has been attenuated (~10x here) and
  reshaped by the specimen, and emerges gradually from the noise floor, so its onset is
  detected late — biasing x2 high. It is filled regardless (the operator asked to always get a
  starting value) but carries a confidence (SNR) so it can be eyeballed and corrected. An
  unverified x2 only shifts the transmitted window; the operator can nudge it in the GUI.

Detection is amplitude/sign agnostic (envelope- and correlation-magnitude based), so the input
polarity (``invert_signals``) does not matter here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .matlab_io import mround

_BASE_N = 80          # pre-trigger samples used to measure the noise baseline
_INC_K = 8.0          # incident onset: threshold in baseline-sigma units
_TRA_K = 3.0          # transmitted onset back-track floor, in baseline-sigma units
_ENV_SMOOTH = 9       # transmitted envelope smoothing window (samples)


@dataclass(frozen=True)
class DistanceEstimate:
    """Auto-estimated gauge distances plus the confidence of each pick.

    ``x1_corr`` is the |normalized cross-correlation| of the reflected match (≈1 is a clean
    lock). ``x2_snr`` is the transmitted-pulse peak envelope over the noise baseline (large is
    confident; near 1 means the transmitted pulse is barely above noise and x2 is unreliable).
    """

    x1: float
    x2: float
    x1_corr: float
    x2_snr: float
    incident_idx: int
    reflected_idx: int
    transmitted_idx: int


def _baseline(sig: np.ndarray, n: int) -> tuple[float, float]:
    seg = sig[: max(2, min(n, len(sig)))]
    return float(seg.mean()), float(seg.std())


def _incident_start(sig: np.ndarray, mu: float, sd: float) -> int:
    """First sample whose deviation from baseline exceeds ``_INC_K`` sigma."""
    if sd <= 0:
        return 0
    cross = np.flatnonzero(np.abs(sig - mu) > _INC_K * sd)
    return int(cross[0]) if cross.size else 0


def _reflected_lag(sig: np.ndarray, i0: int, npoint: int) -> tuple[int, float]:
    """Sliding normalized cross-correlation of the incident window against ``sig``.

    Searches lags past the incident pulse (a half-window guard band skips the self-peak at
    lag 0) and returns the lag of the strongest |correlation| — the reflected return.
    """
    template = sig[i0 : i0 + npoint]
    t = template - template.mean()
    tn = np.linalg.norm(t)
    lo, hi = i0 + npoint // 2, len(sig) - npoint
    if tn == 0 or hi <= lo:
        raise ValueError(
            "could not auto-estimate x1: no room to search for the reflected pulse "
            "(record too short for this npoint?). Set [bar].x1 in hopki.toml."
        )
    best_corr, best_lag = 0.0, None
    for lag in range(lo, hi + 1):
        seg = sig[lag : lag + npoint]
        s = seg - seg.mean()
        sn = np.linalg.norm(s)
        if sn == 0:
            continue
        corr = float(np.dot(t, s) / (tn * sn))
        if abs(corr) > abs(best_corr):
            best_corr, best_lag = corr, lag
    if best_lag is None:
        raise ValueError("could not auto-estimate x1: no reflected pulse found.")
    return best_lag, best_corr


def _transmitted_onset(sig: np.ndarray, after: int, mu: float, sd: float) -> tuple[int, float]:
    """Onset of the transmitted pulse: locate the envelope peak after ``after``, then walk
    back to where the smoothed envelope falls to ``_TRA_K`` baseline-sigma. Returns the onset
    index and the peak-over-noise SNR.
    """
    env = np.convolve(np.abs(sig - mu), np.ones(_ENV_SMOOTH) / _ENV_SMOOTH, mode="same")
    noise = sd if sd > 0 else float(env[:_BASE_N].mean()) or 1.0
    peak = after + int(np.argmax(env[after:]))
    i = peak
    while i > after and env[i] > _TRA_K * noise:
        i -= 1
    return i + 1, float(env[peak] / noise)


def estimate_distances(
    inc_signal: np.ndarray,
    tra_signal: np.ndarray,
    *,
    c0: float,
    tpp: float,
    npoint: int,
    nlong: int | None = None,
    tdelay_us: float = 0.0,
) -> DistanceEstimate:
    """Estimate ``x1`` (gauge-1 → specimen) and ``x2`` (specimen → gauge-2) from the signals.

    ``inc_signal``/``tra_signal`` are the raw incident-bar and transmitted-bar gauge records.
    The transmitted channel is front-padded by the same ``tdelay`` the windowing applies, so
    the measured arrival is referenced to the incident trigger. Distances come from the lags:
    ``x1 = c0 * (t_reflected - t_incident) / 2`` and
    ``x2 = c0 * (t_transmitted - t_incident) - x1``.
    """
    inc = np.asarray(inc_signal, dtype=float).ravel()
    tra = np.asarray(tra_signal, dtype=float).ravel()

    # Match window_pulses' transmitted acquisition-delay padding so arrivals share an origin.
    npdelay = mround(tdelay_us * 1e-6 / tpp)
    if npdelay > 0:
        keep = nlong if nlong is not None else len(tra)
        tra = np.concatenate([np.full(npdelay, tra[0]), tra])[:keep]

    mu_i, sd_i = _baseline(inc, _BASE_N)
    i0 = _incident_start(inc, mu_i, sd_i)

    reflag, corr = _reflected_lag(inc, i0, npoint)
    x1 = c0 * (reflag - i0) * tpp / 2.0

    mu_t, sd_t = _baseline(tra, _BASE_N)
    onset, snr = _transmitted_onset(tra, i0, mu_t, sd_t)
    x2 = c0 * (onset - i0) * tpp - x1
    x2 = max(0.0, x2)  # a negative distance is unphysical; clamp (confidence flags it)

    return DistanceEstimate(
        x1=x1, x2=x2, x1_corr=abs(corr), x2_snr=snr,
        incident_idx=i0, reflected_idx=reflag, transmitted_idx=onset,
    )
