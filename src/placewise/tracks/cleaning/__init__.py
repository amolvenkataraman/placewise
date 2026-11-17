"""Cleaning raw tracks: pure functions Track -> new Track; inputs are never modified.

- steps: sort_and_dedupe, drop_invalid, filter_accuracy, remove_spikes, split_gaps,
  fix_clock_jumps, thin;
- smoothing: smooth (Kalman + RTS) and smooth_elevation (Hampel).

A typical pipeline: drop_invalid -> sort_and_dedupe (or fix_clock_jumps, when the recorded order
is the truth) -> filter_accuracy -> remove_spikes -> split_gaps -> smooth -> thin.
"""

from .smoothing import smooth, smooth_elevation
from .steps import (
    drop_invalid,
    filter_accuracy,
    fix_clock_jumps,
    remove_spikes,
    sort_and_dedupe,
    split_gaps,
    thin,
)

__all__ = [
    "drop_invalid",
    "filter_accuracy",
    "fix_clock_jumps",
    "remove_spikes",
    "smooth",
    "smooth_elevation",
    "sort_and_dedupe",
    "split_gaps",
    "thin",
]
