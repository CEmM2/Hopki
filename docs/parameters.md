# Parameters

This page describes every editable Analysis-tab field and every operator-controlled parameter.

## Experiment Fields

These fields are shown in the **Experiment** box on the Analysis tab.

| Field | Unit | Meaning |
| --- | --- | --- |
| `npoint` | samples | Number of samples in each windowed incident, reflected, and transmitted pulse. |
| `diam_bar` / **bar diameter** | m | Diameter of the incident/transmitted bars. Used to compute bar cross-sectional area and force. |
| `E` | Pa | Bar Young's modulus. Used in force calculation. |
| `x1` | m | Distance from gauge 1 to the specimen. Used to locate the reflected pulse and to apply dispersion correction. |
| `x2` | m | Distance from the specimen to gauge 2. Used to locate the transmitted pulse and to apply dispersion correction. |
| `c0` | m/s | Bar wave speed. Used for pulse timing, velocity, strain rate, and dispersion correction. |
| `gfact` | dimensionless | Strain-gauge factor. Used to convert bridge voltage to strain. |
| `vbridge` | V | Bridge excitation voltage. Used with `gfact` in the voltage-to-strain conversion. |
| `diam_spec` / **specimen diameter** | m | Specimen diameter. Used to compute specimen area and stress. |
| `long_spec` / **specimen length** | m | Specimen length. Used to compute engineering strain rate. |
| `tdelay_us` | microseconds | Acquisition delay for the transmitted signal. Hopki pads the transmitted record by this delay before windowing. |
| `pretr_pct` | percent | Pre-trigger percentage. Used to guess the initial `tim_cut` when an experiment loads. |
| `damp_f` | coefficient | Amplitude damping coefficient used during frequency-domain correction. |

## Derived Values

| Value | Source | Notes |
| --- | --- | --- |
| `tpp` | Signal time column | Time per point. This is intentionally not editable because it belongs to the recorded signal. |
| `x1` estimate | Signals | Used only when `x1` is absent from all config layers. Usually more reliable than `x2`. |
| `x2` estimate | Signals | Used only when `x2` is absent from all config layers. Treat as best-effort and verify with **Pick x2 (2 clicks)** when needed. |

## Operator Parameters

| Parameter | Control | Default | Meaning |
| --- | --- | --- | --- |
| `tim_cut` | Vertical line on **Signals** | Initial guess from `pretr_pct` | Pulse-start time. The incident pulse window starts here; reflected and transmitted windows are positioned from `x1`, `x2`, `c0`, and `tdelay_us`. |
| `invert_signals` | **invert signal polarity** | off | Negates both input channels before analysis. |
| `nu` | **Poisson nu** | `0.29` | Poisson ratio used by the Bancroft phase-velocity table for dispersion correction. |
| `reflect_shift` | **reflect shift** spinbox/slider | `0` | Sample shift applied to the reflected pulse after correction. Positive values delay it; negative values advance it. |

## How Hopki Uses The Values

The core pipeline runs in four stages:

1. **Window pulses** using `tim_cut`, `x1`, `x2`, `c0`, `tdelay_us`, `nlong`, and `npoint`.
2. **Correct dispersion and damping** using `nu`, `diam_bar`, `c0`, `x1`, `x2`, `tpp`, `npoint`, and `damp_f`.
3. **Align the reflected pulse** using `reflect_shift`.
4. **Compute mechanics** using `diam_bar`, `E`, `gfact`, `vbridge`, `diam_spec`, `long_spec`, `c0`, and `tpp`.

## Configuration Files

Modern configuration uses `hopki.toml`. Ancestor files are applied before the experiment-local file, so a campaign-level file can hold shared bar constants and each experiment can hold only specimen-specific values.

```toml
[bar]
nlong = 1000
npoint = 450
diam_bar = 1.27e-2
E = 1.9e11
x1 = 0.558
x2 = 0.230
c0 = 4800
gfact = 2.13
vbridge = 10.15
damp_f = -1.8e-2

[specimen]
diam = 4e-3
length = 4e-3
tdelay_us = 0.0
pretr_pct = 10.0

[signals]
incident = "WAVE0003.FLT"
transmitted = "WAVE0004.FLT"
```

Legacy folders with no `hopki.toml` can still use `incid.exp`, `incid.spec`, and `DAMP_F`.
