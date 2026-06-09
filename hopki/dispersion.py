"""Pochhammer–Chree / Bancroft dispersion correction tables and lookup.

Ports `ban.M` (tabulated phase velocity C/C0 vs a/lambda at four Poisson ratios),
`BAN11.M` (interpolate the table to the bar's Poisson ratio), and `DISPR1.M` (interpolate
phase velocity at a given frequency). The default Poisson ratio is 0.29, matching the
hard-coded value in `BAN11.M`.
"""

from __future__ import annotations

import numpy as np

# ban.M: columns = C/C0 at nu = 0.20, 0.25, 0.30, 0.35, then the a/lambda axis value.
# Only the first 26 rows are used (BAN11 drops the final 1e3 sentinel row).
_BAN = np.array(
    [
        [1.0000000e00, 1.0000000e00, 1.0000000e00, 1.0000000e00, 0.00],
        [9.9975000e-01, 9.9961000e-01, 9.9944000e-01, 9.9924000e-01, 0.05],
        [9.9800000e-01, 9.9843000e-01, 9.9774000e-01, 9.9694000e-01, 0.10],
        [9.9766000e-01, 9.9638000e-01, 9.9482000e-01, 9.9302000e-01, 0.15],
        [9.9568000e-01, 9.9333000e-01, 9.9054000e-01, 9.8732000e-01, 0.20],
        [9.9287000e-01, 9.8909000e-01, 9.8466000e-01, 9.7967000e-01, 0.25],
        [9.8899000e-01, 9.8337000e-01, 9.7691000e-01, 9.6979000e-01, 0.30],
        [9.8366000e-01, 9.7572000e-01, 9.6688000e-01, 9.5739000e-01, 0.35],
        [9.7627000e-01, 9.6559000e-01, 9.5410000e-01, 9.4218000e-01, 0.40],
        [9.6592000e-01, 9.5220000e-01, 9.3810000e-01, 9.2397000e-01, 0.45],
        [9.5133000e-01, 9.3479000e-01, 9.1854000e-01, 9.0277000e-01, 0.50],
        [9.3119000e-01, 9.1288000e-01, 8.9549000e-01, 8.7899000e-01, 0.55],
        [9.0502000e-01, 8.8681000e-01, 8.6964000e-01, 8.5341000e-01, 0.60],
        [8.7432000e-01, 8.5800000e-01, 8.4222000e-01, 8.2709000e-01, 0.65],
        [8.4201000e-01, 8.2841000e-01, 8.1466000e-01, 8.0110000e-01, 0.70],
        [8.1074000e-01, 7.9982000e-01, 7.8818000e-01, 7.7632000e-01, 0.75],
        [7.8202000e-01, 7.7332000e-01, 7.6357000e-01, 7.5330000e-01, 0.80],
        [7.5644000e-01, 7.4943000e-01, 7.4125000e-01, 7.3236000e-01, 0.85],
        [7.3402000e-01, 7.2826000e-01, 7.2130000e-01, 7.1355000e-01, 0.90],
        [7.1454000e-01, 7.0967000e-01, 7.0365000e-01, 6.9682000e-01, 0.95],
        [6.9768000e-01, 6.9344000e-01, 6.8814000e-01, 6.8203000e-01, 1.00],
        [6.5030000e-01, 6.4712000e-01, 6.4321000e-01, 6.3869000e-01, 1.20],
        [6.2361000e-01, 6.2048000e-01, 6.1687000e-01, 6.1284000e-01, 1.40],
        [6.0815000e-01, 6.0479000e-01, 6.0111000e-01, 5.9713000e-01, 1.60],
        [5.9892000e-01, 5.9526000e-01, 5.9139000e-01, 5.8731000e-01, 1.80],
        [5.9326000e-01, 5.8932000e-01, 5.8524000e-01, 5.8101000e-01, 2.00],
        [5.8804000e-01, 5.8148000e-01, 5.7516000e-01, 5.6903000e-01, 1.0e3],
    ]
)

_NU_COLUMNS = (0.20, 0.25, 0.30, 0.35)


def bancroft_table(nu: float = 0.29) -> np.ndarray:
    """Port of `BAN11.M`: interpolate the Bancroft table to Poisson ratio ``nu``.

    Returns a (26, 2) array with columns ``[a/lambda, C/C0]``. The a/lambda axis is the
    raw table value halved, exactly as `BAN11.M` does (``al = ban(:,5)/2``).
    """
    table = _BAN[:26]
    edges = _NU_COLUMNS
    for j in range(len(edges) - 1):
        lo, hi = edges[j], edges[j + 1]
        if lo <= nu <= hi:
            k = (nu - lo) / (hi - lo)
            cc0 = table[:, j] + (table[:, j + 1] - table[:, j]) * k
            break
    else:
        raise ValueError(f"Poisson ratio {nu} outside tabulated range [0.20, 0.35]")
    a_over_lambda = table[:, 4] / 2.0
    return np.column_stack([a_over_lambda, cc0])


def phase_velocity(freq: float, radius: float, c0: float, table: np.ndarray) -> float:
    """Port of `DISPR1.M`: phase velocity at ``freq`` via linear table interpolation.

    ``table`` is the (26, 2) output of :func:`bancroft_table`. Above the tabulated range
    the velocity saturates at ``0.59 * c0`` (the MATLAB fallback).
    """
    f = freq * radius / c0  # normalized frequency a/lambda
    i = 1  # MATLAB 1-based index into the table
    while f >= table[i - 1, 0]:
        i += 1
        if i > 26:
            break
    if i < 26:
        x0, y0 = table[i - 2]
        x1, y1 = table[i - 1]
        return c0 * ((f - x0) * (y1 - y0) / (x1 - x0) + y0)
    return 0.59 * c0
