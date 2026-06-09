"""Layered experiment configuration.

The legacy MATLAB convention split a run's parameters across three magic-named, *positional*
files that every experiment folder had to carry a copy of: ``incid.exp`` (10 unlabeled
numbers), ``incid.spec`` (4 numbers) and ``DAMP_F`` (1 scalar). That conflates three different
lifetimes of data — bar/rig constants, per-specimen values, and processing picks — and encodes
them by line position, so a reordered file silently produces garbage.

This module replaces that with a single labeled ``hopki.toml`` schema resolved in layers, each
overriding the previous::

    code DEFAULTS  ->  bar/campaign hopki.toml  ->  per-experiment hopki.toml  ->  GUI live picks

``hopki.toml`` files are discovered by walking up from the experiment directory, so one file at
a campaign root (the bar constants) serves every shot under it, and a per-experiment file need
only list what differs (typically the specimen dimensions).

For backward compatibility — and so the bundled ``gold`` fixtures keep loading unchanged — a
folder with the legacy positional files and *no* ``hopki.toml`` is read by the legacy shim.

Schema (all keys optional; anything omitted falls through to the layer below)::

    [bar]                          # bar/rig constants -> ExpConfig + damp_f
    nlong = 1000                   #   record length (samples)
    npoint = 450                   #   samples per windowed pulse
    diam_bar = 1.27e-2             #   bar diameter (m)
    E = 1.9e11                     #   bar Young's modulus (Pa)
    x1 = 0.558                     #   gauge-1 -> specimen (m); auto-estimated if omitted
    x2 = 0.230                     #   specimen -> gauge-2 (m); auto-estimated if omitted
    c0 = 4800                      #   bar wave speed (m/s)
    gfact = 2.13                   #   gauge factor
    vbridge = 10.15                #   bridge voltage (V)
    damp_f = -1.8e-2               #   dispersion amplitude-damping coefficient

    [specimen]                     # per-specimen values -> SpecConfig
    diam = 4e-3                    #   (alias of diam_spec)
    length = 4e-3                  #   (alias of long_spec)
    tdelay_us = 0.0
    pretr_pct = 10.0

    [signals]                      # which file is which channel (optional)
    incident = "WAVE0009.FLT"
    transmitted = "WAVE0010.FLT"
"""

from __future__ import annotations

import tomllib
from dataclasses import replace
from pathlib import Path

from .twobar import (
    DEFAULT_DAMP_F,
    ExpConfig,
    SpecConfig,
    load_damp_f,
)

CONFIG_NAME = "hopki.toml"

# ``[bar]`` keys that map 1:1 onto ExpConfig fields. ``nlong``/``npoint`` are ints; the rest float.
# ``tpp`` is intentionally absent: it is a property of the capture, derived from the signal's
# time column (matlab_io.sampling_interval), never read from or written to config.
_EXP_INT_FIELDS = ("nlong", "npoint")
_EXP_FLOAT_FIELDS = ("diam_bar", "E", "x1", "x2", "c0", "gfact", "vbridge")
# ``[specimen]`` keys -> SpecConfig fields (friendly aliases plus the raw field names).
_SPEC_KEYMAP = {
    "diam": "diam_spec", "diam_spec": "diam_spec",
    "length": "long_spec", "long_spec": "long_spec",
    "tdelay_us": "tdelay_us", "pretr_pct": "pretr_pct",
}


def _load_toml(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def _has_legacy(d: Path) -> bool:
    """True when the legacy positional config trio is present."""
    return all((d / name).exists() for name in ("incid.exp", "incid.spec", "DAMP_F"))


def _read_legacy(d: Path) -> tuple[ExpConfig, SpecConfig, float]:
    """Read the legacy ``incid.exp``/``incid.spec``/``DAMP_F`` trio (compat shim)."""
    return (
        ExpConfig.from_file(d / "incid.exp"),
        SpecConfig.from_file(d / "incid.spec"),
        load_damp_f(d / "DAMP_F"),
    )


def _apply_toml(
    data: dict, exp: ExpConfig, spec: SpecConfig, damp_f: float
) -> tuple[ExpConfig, SpecConfig, float]:
    """Overlay one parsed ``hopki.toml`` onto the running config; only present keys override."""
    bar = data.get("bar", {})
    exp_updates: dict[str, float] = {}
    for field in _EXP_INT_FIELDS:
        if field in bar:
            exp_updates[field] = int(bar[field])
    for field in _EXP_FLOAT_FIELDS:
        if field in bar:
            exp_updates[field] = float(bar[field])
    if exp_updates:
        exp = replace(exp, **exp_updates)
    if "damp_f" in bar:
        damp_f = float(bar["damp_f"])

    sp = data.get("specimen", {})
    spec_updates = {
        field: float(sp[key]) for key, field in _SPEC_KEYMAP.items() if key in sp
    }
    if spec_updates:
        spec = replace(spec, **spec_updates)

    return exp, spec, damp_f


def _toml_layers(directory: Path, *, include_local: bool = True) -> list[Path]:
    """``hopki.toml`` files from the experiment dir up to the filesystem root, campaign-first.

    Returned ordered so the closest (experiment-local) file is applied last and therefore wins.
    With ``include_local=False`` the experiment directory's own file is skipped — used to
    compute the inherited baseline when writing per-experiment override deltas.
    """
    dirs = (directory, *directory.parents) if include_local else tuple(directory.parents)
    found = [d / CONFIG_NAME for d in dirs if (d / CONFIG_NAME).exists()]
    found.reverse()  # outermost ancestor first; experiment-local last (highest precedence)
    return found


def resolve_config(directory: str | Path) -> tuple[ExpConfig, SpecConfig, float]:
    """Resolve ``(ExpConfig, SpecConfig, damp_f)`` for an experiment directory.

    Starts from the code defaults and overlays every discovered ``hopki.toml`` layer. When no
    ``hopki.toml`` is found anywhere up the tree, falls back to the legacy positional files in
    ``directory``; if those are absent too, the bare defaults are returned.
    """
    d = Path(directory)
    layers = _toml_layers(d)
    if not layers:
        if _has_legacy(d):
            return _read_legacy(d)
        return ExpConfig.DEFAULTS, SpecConfig.DEFAULTS, DEFAULT_DAMP_F

    exp, spec, damp_f = ExpConfig.DEFAULTS, SpecConfig.DEFAULTS, DEFAULT_DAMP_F
    for layer in layers:
        exp, spec, damp_f = _apply_toml(_load_toml(layer), exp, spec, damp_f)
    return exp, spec, damp_f


def resolve_baseline(directory: str | Path) -> tuple[ExpConfig, SpecConfig, float]:
    """Config inherited by an experiment dir from *outer* layers only (defaults + ancestor
    ``hopki.toml`` files), ignoring its own local file. This is what an override is a delta
    against — saving only the fields that differ from this baseline keeps per-experiment files
    minimal.
    """
    d = Path(directory)
    exp, spec, damp_f = ExpConfig.DEFAULTS, SpecConfig.DEFAULTS, DEFAULT_DAMP_F
    for layer in _toml_layers(d, include_local=False):
        exp, spec, damp_f = _apply_toml(_load_toml(layer), exp, spec, damp_f)
    return exp, spec, damp_f


def present_bar_keys(directory: str | Path) -> set[str]:
    """The ``[bar]`` keys an experiment supplies *explicitly* (across all ``hopki.toml`` layers).

    Used to decide whether a field (notably ``x1``/``x2``) must be auto-estimated from the
    signals: a key absent from every layer falls through to a code default and so should be
    estimated instead. The legacy positional ``incid.exp`` always carries the full set, so a
    legacy experiment (e.g. the bundled gold fixture) reports every bar key and triggers no
    estimation.
    """
    d = Path(directory)
    layers = _toml_layers(d)
    if not layers:
        return set(_EXP_INT_FIELDS + _EXP_FLOAT_FIELDS) if _has_legacy(d) else set()
    keys: set[str] = set()
    for layer in layers:
        keys |= set(_load_toml(layer).get("bar", {}).keys())
    return keys


# ``(SpecConfig field, friendly TOML alias)`` pairs, in emit order, for writing ``[specimen]``.
_SPEC_EMIT = (("diam_spec", "diam"), ("long_spec", "length"),
              ("tdelay_us", "tdelay_us"), ("pretr_pct", "pretr_pct"))


def _fmt(value: float | int) -> str:
    """Round-trippable TOML scalar (ints bare, floats via ``repr``)."""
    return str(value) if isinstance(value, int) else repr(float(value))


def save_overrides(
    directory: str | Path, exp: ExpConfig, spec: SpecConfig, damp_f: float
) -> Path:
    """Write a per-experiment ``hopki.toml`` holding only the fields that differ from the
    inherited baseline (``resolve_baseline``). Any existing ``[signals]`` table in the local
    file is preserved. Returns the written path.
    """
    d = Path(directory)
    base_exp, base_spec, base_damp = resolve_baseline(d)

    bar_lines = [
        f"{field} = {_fmt(getattr(exp, field))}"
        for field in (*_EXP_INT_FIELDS, *_EXP_FLOAT_FIELDS)
        if getattr(exp, field) != getattr(base_exp, field)
    ]
    if damp_f != base_damp:
        bar_lines.append(f"damp_f = {_fmt(damp_f)}")
    spec_lines = [
        f"{alias} = {_fmt(getattr(spec, field))}"
        for field, alias in _SPEC_EMIT
        if getattr(spec, field) != getattr(base_spec, field)
    ]

    local = d / CONFIG_NAME
    signals = _load_toml(local).get("signals", {}) if local.exists() else {}

    out = ["# Per-experiment overrides — only the fields that differ from the inherited",
           "# campaign config (see hopki/config.py for the resolution order)."]
    if bar_lines:
        out += ["", "[bar]", *bar_lines]
    if spec_lines:
        out += ["", "[specimen]", *spec_lines]
    if signals:
        out += ["", "[signals]",
                *(f'{k} = "{v}"' for k, v in signals.items())]
    local.write_text("\n".join(out) + "\n")
    return local


def resolve_signals(directory: str | Path) -> tuple[Path, Path]:
    """Locate the incident and transmitted signal files for an experiment directory.

    Order of preference: an explicit ``[signals]`` table in the experiment-local ``hopki.toml``;
    then ``incid.inc``/``trans.tra``; then the two ``WAVE*.FLT`` files (incident first by name).
    """
    d = Path(directory)

    local = d / CONFIG_NAME
    if local.exists():
        sig = _load_toml(local).get("signals", {})
        if "incident" in sig and "transmitted" in sig:
            return d / sig["incident"], d / sig["transmitted"]

    inc_path, tra_path = d / "incid.inc", d / "trans.tra"
    if inc_path.exists() and tra_path.exists():
        return inc_path, tra_path

    waves = sorted(d.glob("WAVE*.FLT")) + sorted(d.glob("WAVE*.flt"))
    if len(waves) < 2:
        raise FileNotFoundError(
            f"no [signals] table, incid.inc/trans.tra, or >=2 WAVE*.FLT files in {d}"
        )
    return waves[0], waves[1]
