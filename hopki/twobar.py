"""Core split Hopkinson bar analysis — Python port of ``twobar_g.m`` (GUI-free).

The pipeline is four pure stages, each taking its interactive choices as arguments:

    load_signals ─▶ window_pulses(tim_cut) ─▶ dispersion_correct(damp_f, nu)
                 ─▶ shift_reflected(reflect_shift) ─▶ compute_mechanics()

``run_analysis`` chains them. Every human-in-the-loop value from the original GUI
(`tim_cut`, the reflected-pulse slider shift) is an explicit parameter, so a given set of
inputs + parameters reproduces the MATLAB outputs deterministically.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from . import dispersion
from .matlab_io import load_matrix, load_signal, mround, sampling_interval, save_ascii


# --------------------------------------------------------------------------- configs
@dataclass(frozen=True)
class ExpConfig:
    """Bar/experiment parameters from ``incid.exp`` (first 10 values, in order)."""

    nlong: int          # samples in the recorded record
    npoint: int         # samples per windowed pulse
    tpp: float          # time per point (sampling interval, s) — derived from the signal,
                        #   not config; see load_inputs / matlab_io.sampling_interval
    diam_bar: float     # bar diameter (m)
    E: float            # bar Young's modulus (Pa)
    x1: float           # gauge-1 -> specimen distance (m)
    x2: float           # specimen -> gauge-2 distance (m)
    c0: float           # bar bar-wave speed (m/s)
    gfact: float        # strain-gauge factor
    vbridge: float      # bridge excitation voltage (V)

    @classmethod
    def from_file(cls, path: str | Path) -> "ExpConfig":
        v = load_matrix(path).ravel()
        return cls(
            nlong=int(v[0]), npoint=int(v[1]), tpp=float(v[2]), diam_bar=float(v[3]),
            E=float(v[4]), x1=float(v[5]), x2=float(v[6]), c0=float(v[7]),
            gfact=float(v[8]), vbridge=float(v[9]),
        )


@dataclass(frozen=True)
class SpecConfig:
    """Specimen parameters from ``incid.spec``."""

    diam_spec: float        # specimen diameter (m)
    long_spec: float        # specimen length (m)
    tdelay_us: float        # transmitted-signal acquisition delay (microseconds)
    pretr_pct: float        # pre-trigger as a percent of the record

    @classmethod
    def from_file(cls, path: str | Path) -> "SpecConfig":
        v = load_matrix(path).ravel()
        return cls(diam_spec=float(v[0]), long_spec=float(v[1]),
                   tdelay_us=float(v[2]), pretr_pct=float(v[3]))


# Canonical defaults (seeded from the known-good ``tests/analysis`` fixture). These are the
# base layer of ``config.resolve_config``: an experiment folder need only override what
# differs from the standard bar/specimen, instead of carrying a full positional config.
ExpConfig.DEFAULTS = ExpConfig(
    nlong=1000, npoint=450, tpp=0.5e-6, diam_bar=1.27e-2, E=1.9e11,
    x1=0.558, x2=0.230, c0=4800.0, gfact=2.13, vbridge=10.15,
)
SpecConfig.DEFAULTS = SpecConfig(diam_spec=4e-3, long_spec=4e-3, tdelay_us=0.0, pretr_pct=10.0)
DEFAULT_DAMP_F = -1.8e-2


# --------------------------------------------------------------------------- pulses
@dataclass
class Pulses:
    """A triplet of incident / reflected / transmitted pulses on a shared time base."""

    incident: np.ndarray
    reflected: np.ndarray
    transmitted: np.ndarray
    time: np.ndarray


def load_damp_f(path: str | Path) -> float:
    """Read the scalar damping coefficient from a ``DAMP_F`` file."""
    return float(load_matrix(path).ravel()[0])


# --------------------------------------------------------------------------- stage 1
def window_pulses(
    inc_signal: np.ndarray,
    tra_signal: np.ndarray,
    exp: ExpConfig,
    spec: SpecConfig,
    tim_cut: float,
) -> Pulses:
    """Stage 1 (``cls_Callback``): slice the three pulses around the pulse start ``tim_cut``.

    ``tim_cut`` is the pulse-start time the operator clicks in the GUI. Reflected/transmitted
    window starts come from wave propagation: reflected returns after ``2*x1/c0``, transmitted
    arrives after ``(x1+x2)/c0``. Each pulse is baseline-corrected (mean of the 31 samples
    before the cut) and shifted so its first sample is zero.
    """
    tpp, npoint = exp.tpp, exp.npoint
    vc1 = np.asarray(inc_signal, dtype=float).copy()
    vc2 = np.asarray(tra_signal, dtype=float).copy()

    # Transmitted-signal acquisition delay: pad the front with copies of the first sample.
    tdelay = spec.tdelay_us * 1e-6
    npdelay = mround(tdelay / tpp)
    if npdelay > 0:
        vc2 = np.concatenate([np.full(npdelay, vc2[0]), vc2])[: exp.nlong]

    too = mround(tim_cut / tpp)  # 1-based pulse-start index, as in MATLAB

    if too < 1:
        raise ValueError(f"tim_cut={tim_cut:g}s is before the record start")

    # Baseline removal: mean of the up-to-31 samples ending at the cut (vc(too-30:too) in
    # MATLAB). Clamp the start so an early pulse pick stays valid instead of wrapping.
    base = slice(max(0, too - 31), too)
    vc1 = vc1 - vc1[base].mean()
    vc2 = vc2 - vc2[base].mean()

    def window(sig: np.ndarray, start_time: float) -> np.ndarray:
        start = mround(start_time / tpp)  # 1-based
        if start < 1 or start - 1 + npoint > len(sig):
            raise ValueError(
                f"pulse window out of range at tim_cut={tim_cut:g}s "
                f"(needs samples {start}..{start + npoint - 1} of {len(sig)})"
            )
        seg = sig[start - 1:start - 1 + npoint].copy()
        return seg - seg[0]  # shift to zero origin

    incident = window(vc1, tim_cut)
    reflected = window(vc1, tim_cut + 2 * exp.x1 / exp.c0)
    transmitted = window(vc2, tim_cut + (exp.x1 + exp.x2) / exp.c0)
    time = np.arange(npoint) * tpp
    return Pulses(incident, reflected, transmitted, time)


# --------------------------------------------------------------------------- stage 2
def dispersion_correct(pulses: Pulses, exp: ExpConfig, damp_f: float, nu: float = 0.29) -> Pulses:
    """Stage 2 (``corr_calc``): frequency-domain dispersion + amplitude correction.

    Each pulse is FFT'd, phase-shifted by ``±2*pi*f*x*(1/c0 - 1/c(f))`` using the Bancroft
    phase velocity ``c(f)``, inverse-FFT'd, then amplitude-scaled by ``exp(±damp_f*x)``.
    """
    n = exp.npoint
    radius = exp.diam_bar / 2.0
    table = dispersion.bancroft_table(nu)
    dfr = 1.0 / n / exp.tpp
    freqs = np.arange(n) * dfr

    half = n // 2
    c = np.array([dispersion.phase_velocity(freqs[i], radius, exp.c0, table) for i in range(half)])
    base = 2 * np.pi * freqs[:half] * (1.0 / exp.c0 - 1.0 / c)  # phase per unit distance

    def phase(x: float, sign: float) -> np.ndarray:
        ph = np.zeros(n)
        ph[:half] = sign * base * x
        ph[half] = 0.0  # Nyquist
        ph[half + 1:] = -ph[1:half][::-1]  # Hermitian symmetry
        return ph

    def correct(sig: np.ndarray, x: float, sign: float, amp: float) -> np.ndarray:
        spec = np.fft.fft(sig)
        spec = spec * np.exp(1j * phase(x, sign))
        return np.real(np.fft.ifft(spec)) * np.exp(amp * x)

    return Pulses(
        incident=correct(pulses.incident, exp.x1, +1.0, -damp_f),
        reflected=correct(pulses.reflected, exp.x1, -1.0, +damp_f),
        transmitted=correct(pulses.transmitted, exp.x2, -1.0, +damp_f),
        time=pulses.time,
    )


# --------------------------------------------------------------------------- stage 3
def shift_reflected(pulses: Pulses, reflect_shift: int) -> Pulses:
    """Stage 3 (slider): time-align the reflected pulse by ``reflect_shift`` samples.

    Positive shift delays the reflected pulse (prepends zeros); negative advances it. The
    incident and transmitted pulses are untouched. The original ``twobar_g`` slider defaults
    to 0; the bundled gold fixture used a shift of 3.
    """
    ref = pulses.reflected
    out = np.zeros_like(ref)
    k = reflect_shift
    if k >= 0:
        out[k:] = ref[: len(ref) - k] if k < len(ref) else 0.0
    else:
        out[: len(ref) + k] = ref[-k:]
    return Pulses(pulses.incident, out, pulses.transmitted, pulses.time)


# --------------------------------------------------------------------------- stage 4
def simpson_cumulative(y: np.ndarray, dt: float) -> np.ndarray:
    """Port of ``integre1``: cumulative integral with step ``dt``.

    The MATLAB "Simpson" rule subdivides each interval at its midpoint with the midpoint set
    to the average, which collapses to the trapezoidal rule. A leading 0 is prepended.
    """
    increments = (y[:-1] + y[1:]) * dt / 2.0
    return np.concatenate([[0.0], np.cumsum(increments)])


@dataclass
class Mechanics:
    """Final mechanical results. 1-D vectors share the ``time`` base unless noted."""

    time: np.ndarray
    v_striker: np.ndarray       # striker velocity estimate (1-D)
    v_in: np.ndarray
    v_out: np.ndarray
    u_in: np.ndarray
    u_out: np.ndarray
    f_in: np.ndarray
    f_out: np.ndarray
    eps_eng: np.ndarray         # engineering strain
    eps_rate_eng: np.ndarray    # engineering strain rate
    str_eng: np.ndarray         # engineering stress
    eps_true: np.ndarray        # true strain
    str_true: np.ndarray        # true stress
    zzcut: int                  # length after the strain<=1 clip


def compute_mechanics(pulses: Pulses, exp: ExpConfig, spec: SpecConfig) -> Mechanics:
    """Stage 4 (``end1_Callback``): forces, velocities, displacements, stress/strain.

    ``pulses`` are the dispersion-corrected, reflected-aligned signals.
    """
    surf_bar = np.pi * exp.diam_bar**2 / 4.0
    surf_spec = np.pi * spec.diam_spec**2 / 4.0
    gv = exp.gfact * exp.vbridge

    einci = 4.0 * pulses.incident / gv
    eref = 4.0 * pulses.reflected / gv
    etra = 4.0 * pulses.transmitted / gv

    veloc = -2.0 * einci * exp.c0
    v_in = -exp.c0 * (einci - eref)
    v_out = -exp.c0 * etra
    u_in = simpson_cumulative(v_in, exp.tpp)
    u_out = simpson_cumulative(v_out, exp.tpp)

    f_in = -exp.E * surf_bar * (einci + eref)
    f_out = -exp.E * surf_bar * etra

    str_eng = f_out / surf_spec
    eps_rate_eng = (2.0 * exp.c0 / spec.long_spec) * eref
    eps_eng = simpson_cumulative(eps_rate_eng, exp.tpp)

    # Clip where engineering strain reaches 1 (physical / log-domain limit).
    over = np.flatnonzero(1.0 - eps_eng <= 0.0)
    zzcut = int(over[0]) if over.size else len(eps_eng)
    zzcut = min(zzcut, len(str_eng))
    s = slice(0, zzcut)

    e = -eps_eng[s]
    # True strain matches twobar_g.m: eps_true = -log(1 + e) = -log(1 - eps_eng).
    eps_true = -np.log(1.0 + e)
    # True stress: the gold fixture computes str_eng * (1 + eps_eng); the literal
    # twobar_g.m line (`surf/(1+e)`) gives str_eng * (1 - eps_eng), which disagrees with
    # gold (its own comment flags the strain sign as "POSITIVE for plotting but NEGATIVE
    # in reality"). We follow gold.
    surf_inst = surf_spec / (1.0 - e)
    str_true = f_out[s] / surf_inst

    time = np.arange(zzcut) * exp.tpp
    return Mechanics(
        time=time, v_striker=veloc[s], v_in=v_in[s], v_out=v_out[s],
        u_in=u_in[s], u_out=u_out[s], f_in=f_in[s], f_out=f_out[s],
        eps_eng=eps_eng[s], eps_rate_eng=eps_rate_eng[s], str_eng=str_eng[s],
        eps_true=eps_true, str_true=str_true, zzcut=zzcut,
    )


# --------------------------------------------------------------------------- orchestrator
@dataclass
class AnalysisResult:
    """Everything the pipeline produces, for inspection / saving / plotting."""

    windowed: Pulses        # stage 1 (inc_puls / ref_puls / tra_puls)
    corrected: Pulses       # stage 2 (inc_corr / ref_corr / tra_corr)
    aligned: Pulses         # stage 3 (reflected-shifted)
    mechanics: Mechanics    # stage 4


def run_analysis(
    inc_signal: np.ndarray,
    tra_signal: np.ndarray,
    exp: ExpConfig,
    spec: SpecConfig,
    damp_f: float,
    *,
    tim_cut: float,
    reflect_shift: int = 0,
    nu: float = 0.29,
    invert_signals: bool = False,
) -> AnalysisResult:
    """Run the full backend pipeline for one experiment.

    ``tim_cut`` (pulse start) and ``reflect_shift`` (slider alignment) are the operator
    choices that the GUI will eventually supply interactively.

    ``invert_signals`` negates both input channels before analysis. The incident pulse must
    be compressive (negative) for the derived velocities/forces to come out with the right
    sign; some WFT->FLT converters emit the opposite polarity (the bundled ``WAVE00*.FLT``
    fixtures do), so this flag adapts to the source convention.
    """
    if invert_signals:
        inc_signal = -np.asarray(inc_signal, dtype=float)
        tra_signal = -np.asarray(tra_signal, dtype=float)
    windowed = window_pulses(inc_signal, tra_signal, exp, spec, tim_cut)
    corrected = dispersion_correct(windowed, exp, damp_f, nu=nu)
    aligned = shift_reflected(corrected, reflect_shift)
    mechanics = compute_mechanics(aligned, exp, spec)
    return AnalysisResult(windowed, corrected, aligned, mechanics)


def load_inputs(directory: str | Path) -> tuple[np.ndarray, np.ndarray, ExpConfig, SpecConfig, float]:
    """Load a standard experiment directory.

    Config (``ExpConfig``/``SpecConfig``/``damp_f``) is resolved by ``config.resolve_config``:
    code defaults, overridden by any ``hopki.toml`` layers, with the legacy positional files
    (``incid.exp``/``incid.spec``/``DAMP_F``) read as a fallback when no ``hopki.toml`` exists.

    The two signals come from an explicit ``[signals]`` table in ``hopki.toml`` when present,
    else ``incid.inc``/``trans.tra``, else the two ``WAVE*.FLT`` files (incident first by name).

    Two values are *not* taken from config: ``tpp`` is always derived from the incident
    signal's time column (``sampling_interval``), and any of ``x1``/``x2`` absent from every
    config layer is auto-estimated from the signals (``geometry.estimate_distances``) — x1
    robustly, x2 best-effort. Explicitly-configured values (including the legacy positional
    files) are left untouched.
    """
    from . import config  # local import to avoid a module-load cycle (config imports twobar)

    d = Path(directory)
    exp, spec, damp_f = config.resolve_config(d)
    inc_path, tra_path = config.resolve_signals(d)

    inc_signal, inc_time = load_signal(inc_path)
    tra_signal, _ = load_signal(tra_path)

    # tpp is a property of the capture, not a config knob: take it from the time column.
    exp = replace(exp, tpp=sampling_interval(inc_time))

    # Fill any gauge distance the config omits by estimating it from the signals.
    present = config.present_bar_keys(d)
    if "x1" not in present or "x2" not in present:
        from .geometry import estimate_distances

        est = estimate_distances(
            inc_signal, tra_signal, c0=exp.c0, tpp=exp.tpp,
            npoint=exp.npoint, nlong=exp.nlong, tdelay_us=spec.tdelay_us,
        )
        updates = {}
        if "x1" not in present:
            updates["x1"] = est.x1
        if "x2" not in present:
            updates["x2"] = est.x2
        exp = replace(exp, **updates)

    return inc_signal, tra_signal, exp, spec, damp_f


def write_results(
    result: AnalysisResult,
    exp: ExpConfig,
    out_dir: str | Path,
    *,
    tim_cut: float | None = None,
) -> list[Path]:
    """Write the analysis outputs as MATLAB-style ``-ascii`` files (one per gold vector).

    File names and column layouts mirror ``twobar_g.m``: pulses are single-column; the
    force/velocity/displacement/strain-rate files are ``[time, value]``; ``s_e_eng``/
    ``s_e_true`` are ``[strain, stress]``. ``v_in2`` is the single-column ``v_in``.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    w, c, m = result.windowed, result.corrected, result.mechanics
    t = m.time

    written: list[Path] = []

    def emit(name: str, arr: np.ndarray) -> None:
        path = out / name
        save_ascii(path, arr)
        written.append(path)

    emit("tpp", np.array([exp.tpp]))
    if tim_cut is not None:
        emit("tim_cut", np.array([tim_cut]))

    emit("inc_puls", w.incident)
    emit("ref_puls", w.reflected)
    emit("tra_puls", w.transmitted)
    emit("inc_corr", c.incident)
    emit("ref_corr", c.reflected)
    emit("tra_corr", c.transmitted)

    emit("v_in2", m.v_in)
    emit("v_striker", m.v_striker)
    for name, val in [
        ("f_in", m.f_in), ("f_out", m.f_out),
        ("v_in", m.v_in), ("v_out", m.v_out),
        ("u_in", m.u_in), ("u_out", m.u_out),
        ("e_dot", m.eps_rate_eng),
    ]:
        emit(name, np.column_stack([t, val]))
    emit("s_e_eng", np.column_stack([m.eps_eng, m.str_eng]))
    emit("s_e_true", np.column_stack([m.eps_true, m.str_true]))
    return written


def main(argv: list[str] | None = None) -> int:
    """CLI: run the analysis on an experiment directory and write the output vectors."""
    p = argparse.ArgumentParser(
        description="Run the split Hopkinson bar analysis on an experiment directory."
    )
    p.add_argument("directory", type=Path,
                   help="dir with incid.exp, incid.spec, DAMP_F and signal files")
    p.add_argument("--tim-cut", type=float, required=True,
                   help="pulse-start time (s) — the operator's pulse pick")
    p.add_argument("--reflect-shift", type=int, default=0,
                   help="reflected-pulse alignment shift in samples (default 0)")
    p.add_argument("--nu", type=float, default=0.29,
                   help="bar Poisson ratio for the dispersion table (default 0.29)")
    p.add_argument("--invert", action="store_true",
                   help="negate input signals (incident pulse must be compressive)")
    p.add_argument("--out", type=Path, default=None,
                   help="output directory (default: the experiment directory)")
    args = p.parse_args(argv)

    inc, tra, exp, spec, damp_f = load_inputs(args.directory)
    from . import config  # report which gauge distances were auto-estimated, not configured

    present = config.present_bar_keys(args.directory)
    auto = [f"{k}={getattr(exp, k):.4g}m" for k in ("x1", "x2") if k not in present]
    if auto:
        print(f"auto-estimated from signals (verify): {', '.join(auto)}")
    print(f"tpp (from signal): {exp.tpp:.4g}s")
    result = run_analysis(
        inc, tra, exp, spec, damp_f,
        tim_cut=args.tim_cut, reflect_shift=args.reflect_shift,
        nu=args.nu, invert_signals=args.invert,
    )
    out = args.out or args.directory
    written = write_results(result, exp, out, tim_cut=args.tim_cut)
    print(f"wrote {len(written)} files to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
