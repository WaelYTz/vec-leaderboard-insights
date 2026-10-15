"""Read the public Virtual Embryo leaderboard API and store anonymised snapshots.

Only public, unauthenticated endpoints are used (the same ones the
virtualembryo.ai leaderboard page reads).  Team names, affiliations and model
strings are dropped before anything is written to disk: a snapshot keeps only
rank, track, headline, per-metric scores and the time the score was posted.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.virtualembryo.ai/challenge"
USER_AGENT = "vec-leaderboard-insights (+https://github.com/WaelYTz/vec-leaderboard-insights)"
SCHEMA = 1

# Fields kept from each leaderboard row.  Everything else (team, affiliation,
# model) is discarded.
KEEP = ("rank", "track", "headline", "metrics", "scored_at")


def _get(path: str, timeout: float = 30.0, retries: int = 2) -> dict:
    url = API + path
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def anonymise_row(row: dict) -> dict:
    return {k: row.get(k) for k in KEEP}


def fetch_snapshot(get=_get) -> dict:
    """Fetch every board currently listed by the API.  ``get`` is injectable for tests."""
    phase = get("/phase")
    overall = get("/overall")
    snap = {
        "schema": SCHEMA,
        "source": API,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "phase": {k: phase.get(k) for k in ("phase", "label", "split", "board")},
        "boards": {},
    }
    for b in overall["boards"]:
        key, task = b["key"], b["task"]
        q = urllib.parse.urlencode({"task": task, "board": key})
        d = get(f"/leaderboard?{q}")
        snap["boards"][key] = {
            "key": key,
            "task": task,
            "label": b.get("label", key),
            "updated_at": d.get("updated_at"),
            "teams_listed": len(d.get("rows", [])),
            "reference": [
                {"name": r["name"], "headline": r["headline"], "metrics": r.get("metrics", {})}
                for r in d.get("reference", [])
            ],
            "rows": [anonymise_row(r) for r in d.get("rows", [])],
        }
    return snap


def save_snapshot(snap: dict, directory: str | Path) -> Path:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = snap["fetched_at"][:19].replace(":", "").replace("-", "")
    path = directory / f"snapshot_{stamp}Z.json"
    # compact: one snapshot a day for the whole challenge should stay small
    path.write_text(json.dumps(snap, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_snapshot(path: str | Path) -> dict:
    snap = json.loads(Path(path).read_text(encoding="utf-8"))
    if snap.get("schema") != SCHEMA:
        raise ValueError(f"{path}: unsupported snapshot schema {snap.get('schema')!r}")
    return snap


def snapshot_paths(directory: str | Path) -> list[Path]:
    return sorted(Path(directory).glob("snapshot_*.json"))


def latest_snapshot(directory: str | Path) -> dict:
    paths = snapshot_paths(directory)
    if not paths:
        raise FileNotFoundError(f"no snapshot_*.json in {directory}; run `vec-insights snapshot` first")
    return load_snapshot(paths[-1])
