"""Headroom, position and what-if analysis on one leaderboard snapshot.

Everything here is relative to the rows the public leaderboard lists (at most
the top 200 teams per board), so a "percentile" means "share of listed teams".
"""

from __future__ import annotations

from .weights import CEILING, FLOOR, headline, weights_for

FLOOR_NAMES = {"copy_last", "wt_identity"}
NON_BASELINE = FLOOR_NAMES | {"ceiling"}


def quantile(values: list[float], q: float) -> float:
    """Linear-interpolated quantile, q in [0, 1]."""
    if not values:
        return float("nan")
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _top(rows: list[dict], n: int) -> list[dict]:
    return sorted(rows, key=lambda r: -r["headline"])[:n]


def baselines(board: dict) -> dict[str, dict]:
    """Published reference rows that are neither the floor nor the ceiling."""
    return {r["name"]: r for r in board["reference"] if r["name"] not in NON_BASELINE}


def headline_summary(board: dict) -> dict:
    hs = [r["headline"] for r in board["rows"]]
    top = sorted(hs, reverse=True)
    out = {
        "teams_listed": len(hs),
        "best": top[0] if top else float("nan"),
        "rank_10": top[9] if len(top) >= 10 else float("nan"),
        "rank_50": top[49] if len(top) >= 50 else float("nan"),
        "median": quantile(hs, 0.5),
        "last_listed": top[-1] if top else float("nan"),
        "above_floor": sum(h > FLOOR for h in hs),
        "agent_share": (sum(r.get("track") == "agent" for r in board["rows"]) / len(hs)) if hs else float("nan"),
        "baselines": {n: r["headline"] for n, r in baselines(board).items()},
    }
    return out


def metric_headroom(board: dict, top_n: int = 10) -> list[dict]:
    """Per-metric view of where the field stands and where headline points remain.

    ``unclaimed`` is the number of headline points that the median top-N team
    still leaves on the table for this metric:  weight * (100 - top-N median).
    ``spread`` is weight * (p90 - p10) over all listed teams: how strongly this
    metric separates teams today.
    """
    w = weights_for(board["key"])
    rows = board["rows"]
    top = _top(rows, top_n)
    base = baselines(board)
    out = []
    for m, wt in w.items():
        vals = [r["metrics"][m] for r in rows if r["metrics"].get(m) is not None]
        tvals = [r["metrics"][m] for r in top if r["metrics"].get(m) is not None]
        top_med = quantile(tvals, 0.5)
        out.append({
            "metric": m,
            "weight": wt,
            "field_median": quantile(vals, 0.5),
            "field_p90": quantile(vals, 0.9),
            "best": max(vals) if vals else float("nan"),
            "top_median": top_med,
            "at_ceiling_share": (sum(v >= CEILING - 1e-9 for v in vals) / len(vals)) if vals else float("nan"),
            "below_floor_share": (sum(v < FLOOR for v in vals) / len(vals)) if vals else float("nan"),
            "baselines": {n: r["metrics"].get(m) for n, r in base.items()},
            "unclaimed": wt * (CEILING - top_med),
            "spread": wt * (quantile(vals, 0.9) - quantile(vals, 0.1)),
        })
    return out


def estimated_rank(board: dict, value: float) -> int:
    """1 + number of listed teams with a strictly higher headline."""
    return 1 + sum(r["headline"] > value + 1e-9 for r in board["rows"])


def position(board: dict, metrics: dict[str, float], step: float = 5.0,
             published_headline: float | None = None) -> dict:
    """Where a set of scaled metrics would sit on this board, and what-if gains.

    ``metrics`` are the per-metric numbers from your submission page (50 = floor,
    100 = ceiling).  Missing metrics count as 50.  ``published_headline`` lets
    you pass the headline the site showed you; otherwise it is computed.
    """
    w = weights_for(board["key"])
    unknown = sorted(set(metrics) - set(w))
    if unknown:
        raise KeyError(f"metrics not on board {board['key']}: {', '.join(unknown)}; expected {', '.join(w)}")
    h = published_headline if published_headline is not None else headline(board["key"], metrics)
    rank = estimated_rank(board, h)
    rows = board["rows"]
    per_metric = []
    for m, wt in w.items():
        mine = float(metrics.get(m, FLOOR))
        vals = [r["metrics"][m] for r in rows if r["metrics"].get(m) is not None]
        pct = 100.0 * sum(v <= mine for v in vals) / len(vals) if vals else float("nan")
        new_val = min(CEILING, mine + step)
        gain = wt * (new_val - mine)
        per_metric.append({
            "metric": m,
            "weight": wt,
            "yours": mine,
            "percentile": pct,
            "top10_median": quantile([r["metrics"][m] for r in _top(rows, 10) if m in r["metrics"]], 0.5),
            "what_if_value": new_val,
            "headline_gain": gain,
            "what_if_rank": estimated_rank(board, h + gain),
        })
    hs = sorted((r["headline"] for r in rows), reverse=True)
    targets = {}
    for n in (1, 10, 50, 100):
        if len(hs) >= n:
            targets[f"top_{n}"] = max(0.0, hs[n - 1] - h + 1e-4)
    return {
        "board": board["key"],
        "headline": h,
        "estimated_rank": rank,
        "teams_listed": len(rows),
        "step": step,
        "metrics": per_metric,
        "points_needed": targets,
    }


def board_overview(snap: dict) -> list[dict]:
    """One line per board: the numbers most people want first."""
    out = []
    for key, b in snap["boards"].items():
        s = headline_summary(b)
        hr = metric_headroom(b)
        weakest = max(hr, key=lambda x: x["unclaimed"]) if hr else None
        out.append({
            "board": key,
            "label": b.get("label", key),
            **s,
            "biggest_unclaimed_metric": weakest["metric"] if weakest else None,
            "biggest_unclaimed_points": weakest["unclaimed"] if weakest else float("nan"),
        })
    return out
