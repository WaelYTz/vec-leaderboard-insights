"""Synthetic fixtures: the tests never touch the network."""

import pytest

from vec_insights.weights import headline


def _row(key, rank, metrics, track="human"):
    return {"rank": rank, "track": track, "headline": round(headline(key, metrics), 4),
            "metrics": metrics, "scored_at": "2026-10-01T00:00:00+00:00"}


def make_board(key="T1:val", n=20):
    rows = []
    for i in range(n):
        v = 70 - i  # strictly decreasing
        m = {"de_score": v - 10, "de_direction": v, "mmd_u": v + 5, "variogram": v + 2}
        rows.append(_row(key, i + 1, m, "agent" if i % 4 == 0 else "human"))
    return {
        "key": key, "task": "T1", "label": "T1 synthetic", "updated_at": None, "teams_listed": n,
        "reference": [
            {"name": "ceiling", "headline": 100.0, "metrics": {}},
            {"name": "copy_last", "headline": 50.0, "metrics": {}},
            {"name": "pseudobulk_shift", "headline": 48.5,
             "metrics": {"de_score": 46.0, "de_direction": 54.0, "mmd_u": 52.5, "variogram": 39.0}},
        ],
        "rows": rows,
    }


@pytest.fixture
def board():
    return make_board()


@pytest.fixture
def snap():
    t3 = {"de_score": 60, "de_direction": 65, "severity_slope": 100, "mmd_u": 70, "variogram": 75}
    return {
        "schema": 1, "source": "test", "fetched_at": "2026-10-15T00:00:00+00:00",
        "phase": {"phase": "p2", "label": "P2", "split": "val", "board": "validation"},
        "boards": {
            "T1:val": make_board(),
            "T3:gata4": {
                "key": "T3:gata4", "task": "T3", "label": "T3", "updated_at": None, "teams_listed": 1,
                "reference": [{"name": "wt_identity", "headline": 50.0, "metrics": {}}],
                "rows": [_row("T3:gata4", 1, t3)],
            },
        },
    }
