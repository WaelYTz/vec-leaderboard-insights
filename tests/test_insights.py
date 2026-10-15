import json
import math

import pytest

from vec_insights import api, analysis, history, report, weights
from vec_insights.cli import main


# --- weights -----------------------------------------------------------------

def test_weights_sum_to_one():
    for task, w in weights.WEIGHTS.items():
        assert math.isclose(sum(w.values()), 1.0), task


def test_floor_and_ceiling_map_to_50_and_100():
    for task, w in weights.WEIGHTS.items():
        key = f"{task}:x"
        assert math.isclose(weights.headline(key, {m: 50 for m in w}), 50)
        assert math.isclose(weights.headline(key, {m: 100 for m in w}), 100)


def test_missing_metric_counts_as_floor():
    assert math.isclose(weights.headline("T1:val", {}), 50)
    # +10 on de_score only (weight .25) -> 52.5
    assert math.isclose(weights.headline("T1:val", {"de_score": 60}), 52.5)


def test_known_published_row_reproduced():
    # T1:val rank-1 row from the public board on 2026-10-15 (headline 75.9529)
    m = {"de_score": 63.8407, "de_direction": 74.1182, "mmd_u": 84.7145, "variogram": 80.2442}
    assert abs(weights.headline("T1:val", m) - 75.9529) < 1e-3


def test_unknown_task_raises():
    with pytest.raises(KeyError):
        weights.weights_for("T9:val")


def test_formula_check_flags_mismatch(board):
    assert weights.formula_check(board)["rows_off_by_more_than_0.01"] == 0
    board["rows"][0]["headline"] -= 0.5
    chk = weights.formula_check(board)
    assert chk["rows_off_by_more_than_0.01"] == 1
    assert math.isclose(chk["max_abs_error"], 0.5, abs_tol=1e-3)


# --- analysis ----------------------------------------------------------------

def test_quantile():
    assert analysis.quantile([1, 2, 3, 4], 0.5) == 2.5
    assert analysis.quantile([5], 0.9) == 5
    assert math.isnan(analysis.quantile([], 0.5))


def test_headline_summary(board):
    s = analysis.headline_summary(board)
    assert s["teams_listed"] == 20
    assert s["best"] == board["rows"][0]["headline"]
    assert s["rank_10"] == board["rows"][9]["headline"]
    assert math.isnan(s["rank_50"])           # fewer than 50 rows
    assert s["baselines"] == {"pseudobulk_shift": 48.5}  # floor/ceiling excluded
    assert math.isclose(s["agent_share"], 5 / 20)


def test_metric_headroom_unclaimed(board):
    hr = {h["metric"]: h for h in analysis.metric_headroom(board, top_n=10)}
    # top-10 de_score values are 60..51 -> median 55.5 -> unclaimed .25 * 44.5
    assert math.isclose(hr["de_score"]["top_median"], 55.5)
    assert math.isclose(hr["de_score"]["unclaimed"], 0.25 * 44.5)
    assert hr["de_score"]["baselines"]["pseudobulk_shift"] == 46.0
    assert 0 < hr["de_score"]["below_floor_share"] < 1


def test_estimated_rank(board):
    best = board["rows"][0]["headline"]
    assert analysis.estimated_rank(board, best + 1) == 1
    assert analysis.estimated_rank(board, best) == 1          # ties do not push you down
    assert analysis.estimated_rank(board, 0) == 21


def test_position_what_if(board):
    mine = board["rows"][5]["metrics"]
    p = analysis.position(board, mine, step=5)
    assert p["estimated_rank"] == 6
    gains = {m["metric"]: m for m in p["metrics"]}
    assert math.isclose(gains["mmd_u"]["headline_gain"], 1.5)  # 0.30 * 5
    assert gains["mmd_u"]["what_if_rank"] < 6
    assert p["points_needed"]["top_1"] > 0
    assert p["points_needed"]["top_10"] == 0


def test_position_caps_at_ceiling(board):
    p = analysis.position(board, {"de_score": 98, "de_direction": 100, "mmd_u": 100, "variogram": 100})
    g = {m["metric"]: m["headline_gain"] for m in p["metrics"]}
    assert math.isclose(g["de_score"], 0.25 * 2)
    assert g["mmd_u"] == 0


def test_position_rejects_unknown_metric(board):
    with pytest.raises(KeyError):
        analysis.position(board, {"severity_slope": 60})


def test_published_headline_overrides(board):
    p = analysis.position(board, {"de_score": 50}, published_headline=1000)
    assert p["estimated_rank"] == 1


# --- api (no network: the getter is injected) ----------------------------------

def _fake_get(path):
    if path == "/phase":
        return {"phase": "p2", "label": "P2", "split": "val", "board": "validation", "daily_quota": 8}
    if path == "/overall":
        return {"boards": [{"key": "T1:val", "task": "T1", "label": "T1 · single-cell temporal"}]}
    assert path.startswith("/leaderboard?") and "board=T1%3Aval" in path
    return {
        "updated_at": "2026-10-15T00:00:00+00:00",
        "reference": [{"name": "copy_last", "headline": 50.0, "metrics": {"de_score": 50.0}}],
        "rows": [{"rank": 1, "team": "Secret Team", "affiliation": "Secret Uni", "model": "secret-model",
                  "track": "human", "headline": 60.0, "metrics": {"de_score": 60.0},
                  "scored_at": "2026-10-14T00:00:00+00:00"}],
    }


def test_fetch_snapshot_anonymises(tmp_path):
    snap = api.fetch_snapshot(get=_fake_get)
    text = json.dumps(snap)
    for secret in ("Secret Team", "Secret Uni", "secret-model", "affiliation", '"team"', '"model"'):
        assert secret not in text
    row = snap["boards"]["T1:val"]["rows"][0]
    assert set(row) == set(api.KEEP)
    path = api.save_snapshot(snap, tmp_path)
    assert api.load_snapshot(path)["boards"]["T1:val"]["rows"][0]["headline"] == 60.0
    assert api.latest_snapshot(tmp_path)["fetched_at"] == snap["fetched_at"]


def test_load_rejects_unknown_schema(tmp_path):
    p = tmp_path / "snapshot_x.json"
    p.write_text(json.dumps({"schema": 99}))
    with pytest.raises(ValueError):
        api.load_snapshot(p)


def test_latest_snapshot_missing_dir(tmp_path):
    with pytest.raises(FileNotFoundError):
        api.latest_snapshot(tmp_path)


# --- history -------------------------------------------------------------------

def test_history_is_chronological(snap):
    later = json.loads(json.dumps(snap))
    later["fetched_at"] = "2026-10-16T00:00:00+00:00"
    for r in later["boards"]["T1:val"]["rows"]:
        r["headline"] += 1
    h = history.board_history([later, snap])["T1:val"]
    assert [p["fetched_at"][:10] for p in h] == ["2026-10-15", "2026-10-16"]
    assert math.isclose(h[1]["best"] - h[0]["best"], 1)


# --- reports and CLI ---------------------------------------------------------------

def test_markdown_reports(snap):
    o = report.overview_markdown(snap)
    assert "T1:val" in o and "T3:gata4" in o
    h = report.headroom_markdown(snap, "T1:val")
    assert "Unclaimed" in h and "pseudobulk_shift" in h and "20/20" in h
    w = report.position_markdown(snap, "T1:val", {"de_score": 55})
    assert "estimated rank" in w


def test_html_dashboard_is_self_contained(snap):
    html = report.html_dashboard(snap, {})
    assert "/*__DATA__*/null" not in html
    assert "http://" not in html.replace("http://www.w3.org/2000/svg", "")
    assert "<script src" not in html and "<link" not in html
    start = html.index("const DATA = ") + len("const DATA = ")
    payload = json.loads(html[start:html.index(";\nconst NS")])
    assert set(payload["boards"]) == {"T1:val", "T3:gata4"}
    assert payload["boards"]["T1:val"]["summary"]["rank_50"] is None   # NaN -> null


def test_cli_end_to_end(snap, tmp_path, capsys):
    d = tmp_path / "snaps"
    api.save_snapshot(snap, d)
    assert main(["overview", "--dir", str(d)]) == 0
    assert main(["headroom", "--dir", str(d), "--board", "T3:gata4"]) == 0
    assert main(["whereami", "--dir", str(d), "--board", "T1:val",
                 "--metrics", "de_score=55", "mmd_u=66", "--step", "2"]) == 0
    out = tmp_path / "site" / "index.html"
    assert main(["dashboard", "--dir", str(d), "--out", str(out)]) == 0
    assert out.exists()
    text = capsys.readouterr().out
    assert "Where you stand on T1:val" in text


def test_cli_errors(snap, tmp_path):
    d = tmp_path / "snaps"
    api.save_snapshot(snap, d)
    with pytest.raises(SystemExit):
        main(["whereami", "--dir", str(d), "--board", "T1:val", "--metrics", "nope=1"])
    with pytest.raises(SystemExit):
        main(["whereami", "--dir", str(d), "--board", "T1:val", "--metrics", "de_score"])
    with pytest.raises(SystemExit):
        main(["headroom", "--dir", str(d), "--board", "T7:missing"])
