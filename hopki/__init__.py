"""Hopki — split Hopkinson bar analysis (Python port of the MATLAB twobar_g suite).

The backend is intentionally GUI-free: every stage is a pure function that takes its
human-in-the-loop choices (pulse-start time, reflected-pulse shift, filter cutoff) as
explicit arguments, so the pipeline is deterministic and testable against the MATLAB
`gold/` fixtures. A GUI can later supply these arguments interactively.
"""

from __future__ import annotations
