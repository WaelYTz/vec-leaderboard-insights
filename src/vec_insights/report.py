"""Plain-text (Markdown) and HTML reports."""

from __future__ import annotations

import json
from importlib import resources

from .analysis import board_overview, headline_summary, metric_headroom, position
from .weights import METRIC_LABELS, formula_check


def _f(x: float, nd: int = 1) -> str:
    return "–" if x != x else f"{x:.{nd}f}"  # x != x  <=> NaN


def _label(m: str) -> str:
    return f"{METRIC_LABELS.get(m, m)} (`{m}`)"


def overview_markdown(snap: dict) -> str:
    lines = [
        f"# Virtual Embryo leaderboard snapshot — {snap['fetched_at']}",
        "",
        f"Phase: {snap['phase'].get('label') or snap['phase'].get('phase')}. "
        "Scores use the official scale (floor = 50, ceiling = 100). "
        "Ranks and percentiles are relative to the teams the public board lists.",
        "",
        "| Board | Teams listed | Best | 10th | 50th | Median | Above floor | Best published baseline | Most unclaimed points |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for o in board_overview(snap):
        base = max(o["baselines"].values(), default=float("nan"))
        lines.append(
            f"| {o['board']} | {o['teams_listed']} | {_f(o['best'])} | {_f(o['rank_10'])} | {_f(o['rank_50'])} | "
            f"{_f(o['median'])} | {o['above_floor']} | {_f(base)} | "
            f"`{o['biggest_unclaimed_metric']}` ({_f(o['biggest_unclaimed_points'], 2)} pts) |"
        )
    return "\n".join(lines) + "\n"


def headroom_markdown(snap: dict, board_key: str, top_n: int = 10) -> str:
    b = snap["boards"][board_key]
    s = headline_summary(b)
    hr = sorted(metric_headroom(b, top_n), key=lambda x: -x["unclaimed"])
    chk = formula_check(b)
    base_names = list(s["baselines"])
    lines = [
        f"## {board_key} — {b.get('label', '')}",
        "",
        f"{s['teams_listed']} teams listed; best {_f(s['best'], 2)}, 10th {_f(s['rank_10'], 2)}, "
        f"median {_f(s['median'], 2)}; {s['above_floor']} above the floor (50). "
        + ("Published baselines: " + ", ".join(f"{n} {_f(v, 2)}" for n, v in s["baselines"].items()) + "."
           if s["baselines"] else ""),
        "",
        f"Sorted by **unclaimed** = weight × (100 − top-{top_n} median): headline points even the leading "
        "teams have not captured yet. **Spread** = weight × (p90 − p10): how much this metric separates teams now.",
        "",
        "| Metric | Weight | Field median | Top-10 median | Best | At 100 | Below 50 | "
        + "".join(f"{n} | " for n in base_names) + "Unclaimed | Spread |",
        "|---|---:|---:|---:|---:|---:|---:|" + "---:|" * len(base_names) + "---:|---:|",
    ]
    for h in hr:
        lines.append(
            f"| {_label(h['metric'])} | {h['weight']:.3f} | {_f(h['field_median'])} | {_f(h['top_median'])} | "
            f"{_f(h['best'])} | {h['at_ceiling_share']:.0%} | {h['below_floor_share']:.0%} | "
            + "".join(f"{_f(h['baselines'].get(n) if h['baselines'].get(n) is not None else float('nan'))} | "
                      for n in base_names)
            + f"{_f(h['unclaimed'], 2)} | {_f(h['spread'], 2)} |"
        )
    lines += [
        "",
        f"Formula check: the weights reproduce {chk['rows'] - chk['rows_off_by_more_than_0.01']}/{chk['rows']} "
        f"published headlines to 0.01 (max deviation {chk['max_abs_error']:.3f}).",
        "",
    ]
    return "\n".join(lines)


def position_markdown(snap: dict, board_key: str, metrics: dict[str, float], step: float = 5.0,
                      published_headline: float | None = None) -> str:
    b = snap["boards"][board_key]
    p = position(b, metrics, step, published_headline)
    lines = [
        f"## Where you stand on {board_key}",
        "",
        f"Headline **{p['headline']:.2f}** → estimated rank **{p['estimated_rank']}** of "
        f"{p['teams_listed']} listed teams (snapshot {snap['fetched_at']}).",
        "",
        "Points needed: " + ", ".join(f"{k.replace('_', ' ')} +{v:.2f}" for k, v in p["points_needed"].items()),
        "",
        f"What if you gained {step:g} points on one metric (capped at 100)?",
        "",
        "| Metric | Weight | Yours | Percentile | Top-10 median | Headline gain | New est. rank |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for m in sorted(p["metrics"], key=lambda x: -x["headline_gain"]):
        lines.append(
            f"| {_label(m['metric'])} | {m['weight']:.3f} | {m['yours']:.1f} | {m['percentile']:.0f}% | "
            f"{_f(m['top10_median'])} | +{m['headline_gain']:.2f} | {m['what_if_rank']} |"
        )
    lines += [
        "",
        "The rank is an estimate against the listed teams in this snapshot; the field keeps moving, "
        "and the hidden test set can rank teams differently from validation.",
        "",
    ]
    return "\n".join(lines)


def _no_nan(x):
    """NaN is not valid JSON; the page treats null as 'not available'."""
    if isinstance(x, float) and x != x:
        return None
    if isinstance(x, dict):
        return {k: _no_nan(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_no_nan(v) for v in x]
    return x


def html_dashboard(snap: dict, history: dict | None = None) -> str:
    """Self-contained HTML page (no external requests) with charts and a calculator."""
    payload = {
        "fetched_at": snap["fetched_at"],
        "phase": snap["phase"],
        "boards": {},
        "history": history or {},
        "labels": METRIC_LABELS,
    }
    for key, b in snap["boards"].items():
        payload["boards"][key] = {
            "key": key,
            "label": b.get("label", key),
            "summary": headline_summary(b),
            "headroom": metric_headroom(b),
            "formula": formula_check(b),
            "weights": {h["metric"]: h["weight"] for h in metric_headroom(b)},
            # anonymised rows: only headline + metrics are needed in the browser
            "rows": [{"h": r["headline"], "t": r.get("track"), "m": r["metrics"]} for r in b["rows"]],
        }
    data = json.dumps(_no_nan(payload), ensure_ascii=False, allow_nan=False, default=str).replace("</", "<\\/")
    template = resources.files("vec_insights").joinpath("dashboard_template.html").read_text(encoding="utf-8")
    return template.replace("/*__DATA__*/null", data)
