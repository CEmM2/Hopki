"""Headless state/controller for the Hopki GUI.

Holds the loaded experiment, the operator parameters (``tim_cut``, ``reflect_shift``, ``nu``,
``invert_signals``), and the latest :class:`~hopki.twobar.AnalysisResult`. Every parameter
change calls back into the pure pipeline. No Qt import here, so this is unit-testable without
a display — the view (``hopki.gui.app``) is a thin shell over this.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from hopki import twobar


@dataclass
class Controller:
    directory: Path | None = None
    inc_signal: np.ndarray | None = None
    tra_signal: np.ndarray | None = None
    time: np.ndarray | None = None
    exp: twobar.ExpConfig | None = None
    spec: twobar.SpecConfig | None = None
    damp_f: float = 0.0

    # operator parameters (the GUI's interactive picks)
    tim_cut: float = 0.0
    reflect_shift: int = 0
    nu: float = 0.29
    invert_signals: bool = False

    # which gauge distances were auto-estimated (absent from config) rather than configured
    x1_estimated: bool = False
    x2_estimated: bool = False

    # latest pipeline output / error
    result: twobar.AnalysisResult | None = None
    error: str | None = None

    @property
    def loaded(self) -> bool:
        return self.exp is not None

    def load(self, directory: str | Path) -> None:
        """Load an experiment directory and compute an initial result."""
        from hopki import config

        inc, tra, exp, spec, damp = twobar.load_inputs(directory)
        self.directory = Path(directory)
        self.inc_signal, self.tra_signal = inc, tra
        self.exp, self.spec, self.damp_f = exp, spec, damp
        present = config.present_bar_keys(self.directory)
        self.x1_estimated = "x1" not in present
        self.x2_estimated = "x2" not in present
        self.time = np.arange(len(inc)) * exp.tpp

        # Initial pulse-start guess: the configured pre-trigger time, clamped to a window
        # that keeps every slice in range, so the first render succeeds. The marker itself is
        # unbounded (tim_cut_range spans the record) — the operator may drag it anywhere.
        guess = 1e-2 * spec.pretr_pct * exp.tpp * exp.nlong
        valid_hi = (exp.nlong - exp.npoint) * exp.tpp - 2 * exp.x1 / exp.c0
        self.tim_cut = float(np.clip(guess, exp.tpp, max(exp.tpp, valid_hi)))
        self.recompute()

    def update_config(self, exp: twobar.ExpConfig, spec: twobar.SpecConfig, damp_f: float) -> None:
        """Apply edited configuration, re-clamp ``tim_cut`` to the data range, recompute."""
        self.exp, self.spec, self.damp_f = exp, spec, damp_f
        self.time = np.arange(len(self.inc_signal)) * exp.tpp
        lo, hi = self.tim_cut_range()
        self.tim_cut = float(np.clip(self.tim_cut, lo, hi))
        self.recompute()

    def reload_config(self) -> None:
        """Re-resolve config from disk (hopki.toml layers, or the legacy files), discarding edits.

        ``tpp`` is re-taken from the (unchanged) signal, and any gauge distance still absent
        from config is re-estimated — so reload restores the same derived state as the initial
        load, and reflects distances that a prior Save has since written to ``hopki.toml``.
        """
        if self.directory is None:
            return
        from hopki import config

        exp, spec, damp_f = config.resolve_config(self.directory)
        present = config.present_bar_keys(self.directory)
        self.x1_estimated = "x1" not in present
        self.x2_estimated = "x2" not in present
        exp = replace(exp, tpp=self.exp.tpp)  # tpp is signal-derived; the signal hasn't changed
        if self.x1_estimated or self.x2_estimated:
            from hopki.geometry import estimate_distances

            est = estimate_distances(
                self.inc_signal, self.tra_signal, c0=exp.c0, tpp=exp.tpp,
                npoint=exp.npoint, nlong=exp.nlong, tdelay_us=spec.tdelay_us,
            )
            upd = {}
            if self.x1_estimated:
                upd["x1"] = est.x1
            if self.x2_estimated:
                upd["x2"] = est.x2
            exp = replace(exp, **upd)
        self.update_config(exp, spec, damp_f)

    def save_config(self) -> Path:
        """Persist the current config as a per-experiment ``hopki.toml`` of override deltas."""
        if self.directory is None:
            raise RuntimeError("no experiment loaded")
        from hopki import config

        path = config.save_overrides(self.directory, self.exp, self.spec, self.damp_f)
        # distances just written to hopki.toml are now configured, not estimates
        present = config.present_bar_keys(self.directory)
        self.x1_estimated = "x1" not in present
        self.x2_estimated = "x2" not in present
        return path

    def estimate_geometry(self) -> "object":
        """Run the distance estimator on the currently loaded signals (does not apply).

        Returns a :class:`~hopki.geometry.DistanceEstimate` (with x1/x2 and their confidences).
        Used by the GUI's *Re-estimate* button to re-derive distances even when config already
        supplies them — e.g. when a TOML's x1/x2 are stale from an older setup.
        """
        if not self.loaded:
            raise RuntimeError("no experiment loaded")
        from hopki.geometry import estimate_distances

        return estimate_distances(
            self.inc_signal, self.tra_signal, c0=self.exp.c0, tpp=self.exp.tpp,
            npoint=self.exp.npoint, nlong=self.exp.nlong, tdelay_us=self.spec.tdelay_us,
        )

    def set_distances(
        self, *, x1: float | None = None, x2: float | None = None,
        x1_estimated: bool | None = None, x2_estimated: bool | None = None,
    ) -> None:
        """Apply new gauge distance(s) and recompute, optionally updating the 'estimated' flags.

        A re-estimate sets the flags True (the value is unverified again); a manual 2-click pick
        sets the relevant flag False (the operator deliberately placed it).
        """
        upd: dict[str, float] = {}
        if x1 is not None:
            upd["x1"] = float(x1)
        if x2 is not None:
            upd["x2"] = float(x2)
        if upd:
            self.exp = replace(self.exp, **upd)
        if x1_estimated is not None:
            self.x1_estimated = x1_estimated
        if x2_estimated is not None:
            self.x2_estimated = x2_estimated
        self.recompute()

    def x2_from_picks(self, t_incident: float, t_transmitted: float) -> float:
        """Compute (and apply) x2 from two clicked arrival times on the raw Signals plot.

        The transmitted pulse reaches gauge 2 at ``tim_cut + (x1+x2)/c0`` in the trigger frame;
        the raw transmitted record is shifted earlier by the acquisition delay ``tdelay``, so a
        click at raw time ``t_transmitted`` and an incident-arrival click at ``t_incident`` give
        ``(x1+x2)/c0 = (t_transmitted - t_incident) + tdelay`` → solve for x2 (clamped ≥ 0).
        x1 is taken as currently configured; the pick marks x2 as operator-verified.
        """
        if not self.loaded:
            raise RuntimeError("no experiment loaded")
        tdelay = self.spec.tdelay_us * 1e-6
        x2 = self.exp.c0 * ((t_transmitted - t_incident) + tdelay) - self.exp.x1
        x2 = max(0.0, x2)
        self.set_distances(x2=x2, x2_estimated=False)
        return x2

    def tim_cut_range(self) -> tuple[float, float]:
        """Span the marker may take — the whole record. An out-of-range pulse window then
        surfaces as an error from ``recompute`` rather than being prevented up front."""
        e = self.exp
        assert e is not None
        return 0.0, (e.nlong - 1) * e.tpp

    def recompute(self) -> None:
        """Re-run the pipeline with the current parameters; capture errors for the UI."""
        if not self.loaded:
            return
        try:
            self.result = twobar.run_analysis(
                self.inc_signal, self.tra_signal, self.exp, self.spec, self.damp_f,
                tim_cut=self.tim_cut, reflect_shift=self.reflect_shift,
                nu=self.nu, invert_signals=self.invert_signals,
            )
            self.error = None
        except Exception as exc:  # shown in the status bar, never silently dropped
            self.result = None
            self.error = f"{type(exc).__name__}: {exc}"

    def display_signals(self) -> tuple[np.ndarray, np.ndarray]:
        """Incident/transmitted signals as displayed (respecting the polarity toggle)."""
        sign = -1.0 if self.invert_signals else 1.0
        return sign * self.inc_signal, sign * self.tra_signal

    def export(self, out_dir: str | Path) -> list[Path]:
        """Write the current result to MATLAB-style ``-ascii`` files."""
        if self.result is None:
            raise RuntimeError(self.error or "no result to export; load an experiment first")
        return twobar.write_results(self.result, self.exp, out_dir, tim_cut=self.tim_cut)
