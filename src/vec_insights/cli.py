"""Command line: vec-insights {snapshot,overview,headroom,whereami,dashboard}."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .api import fetch_snapshot, latest_snapshot, load_snapshot, save_snapshot
from .history import load_history
from .report import headroom_markdown, html_dashboard, overview_markdown, position_markdown
from .weights import weights_for


def _load(args) -> dict:
    if args.snapshot:
        return load_snapshot(args.snapshot)
    if args.live:
        return fetch_snapshot()
    return latest_snapshot(args.dir)


def _board(snap: dict, key: str | None) -> list[str]:
    if key is None:
        return list(snap["boards"])
    if key not in snap["boards"]:
        raise SystemExit(f"board {key!r} not in snapshot; available: {', '.join(snap['boards'])}")
    return [key]


def _parse_metrics(items: list[str], board_key: str) -> dict[str, float]:
    out = {}
    for it in items:
        if "=" not in it:
            raise SystemExit(f"expected metric=value, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = float(v)
    unknown = set(out) - set(weights_for(board_key))
    if unknown:
        raise SystemExit(f"unknown metric(s) for {board_key}: {', '.join(sorted(unknown))}; "
                         f"expected: {', '.join(weights_for(board_key))}")
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="vec-insights", description=(
        "Headroom and rank what-ifs from the public Virtual Embryo Challenge leaderboard."))
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def source(sp):
        g = sp.add_mutually_exclusive_group()
        g.add_argument("--snapshot", help="read this snapshot file")
        g.add_argument("--live", action="store_true", help="fetch the board now instead of reading a snapshot")
        sp.add_argument("--dir", default="snapshots", help="snapshot directory (default: snapshots)")

    sp = sub.add_parser("snapshot", help="fetch the public board and save an anonymised snapshot")
    sp.add_argument("--dir", default="snapshots")

    sp = sub.add_parser("overview", help="one line per board")
    source(sp)

    sp = sub.add_parser("headroom", help="per-metric headroom table")
    source(sp)
    sp.add_argument("--board", help="e.g. T1:val (default: all boards)")
    sp.add_argument("--top", type=int, default=10, help="size of the leading group (default 10)")

    sp = sub.add_parser("whereami", help="estimated rank and what-if gains for your metrics")
    source(sp)
    sp.add_argument("--board", required=True)
    sp.add_argument("--metrics", nargs="+", required=True, metavar="NAME=VALUE",
                    help="scaled metrics from your submission page, e.g. de_score=58.2 mmd_u=74")
    sp.add_argument("--headline", type=float, help="headline the site showed you (default: computed)")
    sp.add_argument("--step", type=float, default=5.0, help="what-if gain per metric (default 5)")

    sp = sub.add_parser("dashboard", help="write the self-contained HTML dashboard")
    source(sp)
    sp.add_argument("--out", default="docs/index.html")

    args = p.parse_args(argv)

    if args.cmd == "snapshot":
        snap = fetch_snapshot()
        path = save_snapshot(snap, args.dir)
        print(f"saved {path} ({len(snap['boards'])} boards, phase {snap['phase'].get('phase')})")
        return 0

    snap = _load(args)
    if args.cmd == "overview":
        print(overview_markdown(snap))
    elif args.cmd == "headroom":
        for key in _board(snap, args.board):
            print(headroom_markdown(snap, key, args.top))
    elif args.cmd == "whereami":
        key = _board(snap, args.board)[0]
        print(position_markdown(snap, key, _parse_metrics(args.metrics, key), args.step, args.headline))
    elif args.cmd == "dashboard":
        history = load_history(args.dir) if Path(args.dir).is_dir() else {}
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html_dashboard(snap, history), encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
