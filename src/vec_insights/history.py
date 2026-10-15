"""Trends across several snapshots (e.g. the daily ones the GitHub Action records)."""

from __future__ import annotations

from pathlib import Path

from .analysis import headline_summary
from .api import load_snapshot, snapshot_paths


def board_history(snapshots: list[dict]) -> dict[str, list[dict]]:
    """board key -> chronological list of headline summaries."""
    out: dict[str, list[dict]] = {}
    for snap in sorted(snapshots, key=lambda s: s["fetched_at"]):
        for key, b in snap["boards"].items():
            s = headline_summary(b)
            out.setdefault(key, []).append({
                "fetched_at": snap["fetched_at"],
                "phase": snap.get("phase", {}).get("phase"),
                "best": s["best"],
                "rank_10": s["rank_10"],
                "rank_50": s["rank_50"],
                "median": s["median"],
                "teams_listed": s["teams_listed"],
                "above_floor": s["above_floor"],
            })
    return out


def load_history(directory: str | Path) -> dict[str, list[dict]]:
    return board_history([load_snapshot(p) for p in snapshot_paths(directory)])
