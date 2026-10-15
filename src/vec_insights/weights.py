"""Headline weights for each task's metric panel.

The Virtual Embryo Challenge publishes every metric on a common scale where the
floor model (copy_last / wt_identity) scores 50 and the split-half ceiling scores
100.  A board's *headline* is a fixed weighted sum of those scaled metrics.

The weights below come from the task pages' group weights
(virtualembryo.ai/challenge/tasks) and were checked against the public
leaderboard API: they reproduce the published headline to within 0.0001 for
every row on T1:val, T2:embryo:val_interp and T3:gata4 (snapshot 2026-10-15).
On the two T2 heart boards a minority of rows sit up to ~1 point *below* the
formula, which suggests a component that the public API does not expose.  Use
:func:`formula_check` to measure this on any snapshot.
"""

from __future__ import annotations

# Metric -> weight.  Each task's weights sum to 1.
WEIGHTS: dict[str, dict[str, float]] = {
    "T1": {
        "de_score": 0.25,       # DE gene recovery          25%
        "de_direction": 0.25,   # change direction          25%
        "mmd_u": 0.30,          # cell-state distribution   30%
        "variogram": 0.20,      # gene-gene co-variation    20%
    },
    "T2": {
        # expression change 25%
        "de_score": 0.125,
        "de_direction": 0.125,
        # cell-state distribution 25%
        "mmd_u": 0.15,
        "variogram": 0.10,
        # tissue shape and growth scale 25%
        "d2_shape": 1 / 12,
        "occupancy_dice": 1 / 12,
        "scale_log_ratio": 1 / 12,
        # local spatial organisation 25%
        "neighborhood_mmd": 0.25,
    },
    "T3": {
        "de_score": 0.30,        # response gene recovery   30%
        "de_direction": 0.25,    # response direction       25%
        "severity_slope": 0.25,  # response magnitude       25%
        "mmd_u": 0.12,           # cell-state distribution  20%
        "variogram": 0.08,
    },
}

# Human-readable names, used in reports.
METRIC_LABELS: dict[str, str] = {
    "de_score": "DE gene recovery",
    "de_direction": "Change direction",
    "severity_slope": "Response magnitude",
    "mmd_u": "Cell-state distribution (MMD)",
    "variogram": "Gene-gene co-variation",
    "d2_shape": "Tissue shape (D2)",
    "occupancy_dice": "Spatial occupancy (Dice)",
    "scale_log_ratio": "Growth scale",
    "neighborhood_mmd": "Local spatial organisation",
}

FLOOR = 50.0
CEILING = 100.0


def task_of(board_key: str) -> str:
    """'T2:heart:val_extrap' -> 'T2'."""
    return board_key.split(":", 1)[0]


def weights_for(board_key: str) -> dict[str, float]:
    task = task_of(board_key)
    if task not in WEIGHTS:
        raise KeyError(f"no headline weights known for task {task!r} (board {board_key!r})")
    return WEIGHTS[task]


def headline(board_key: str, metrics: dict[str, float]) -> float:
    """Weighted headline from scaled metrics.

    A metric that is missing counts as zero skill, i.e. the floor value 50
    (the FAQ: a metric your output cannot produce "counts as zero skill").
    """
    w = weights_for(board_key)
    return sum(wt * float(metrics.get(m, FLOOR)) for m, wt in w.items())


def formula_check(board: dict) -> dict:
    """Compare published headlines with :func:`headline` for every row of a board."""
    errors = [
        row["headline"] - headline(board["key"], row["metrics"])
        for row in board["rows"]
        if row.get("headline") is not None
    ]
    off = [e for e in errors if abs(e) > 0.01]
    return {
        "rows": len(errors),
        "rows_off_by_more_than_0.01": len(off),
        "max_abs_error": max((abs(e) for e in errors), default=0.0),
    }
