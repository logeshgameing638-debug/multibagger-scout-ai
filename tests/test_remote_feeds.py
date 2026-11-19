"""Remote-first loading keeps committed automation feeds visible on fresh
sessions even when the hosted app serves a stale on-disk copy (redeploy
without process restart)."""
import json
from pathlib import Path
from unittest import mock

import services.snapshots as snapshots


class FakeResp:
    def __init__(self, payload, ok=True):
        self._payload = payload
        self.ok = ok

    def json(self):
        return self._payload


def _fresh(monkeypatch):
    snapshots._remote_cache.clear()


def test_remote_wins_over_stale_local(tmp_path, monkeypatch):
    _fresh(monkeypatch)
    local = tmp_path / "alerts_feed.json"
    local.write_text(json.dumps({"generated_at": "old", "alerts": []}))
    remote = {"generated_at": "new", "alerts": [{"symbol": "ABB"}]}
    monkeypatch.setattr(snapshots, "AUTOMATION_FEED_FILE", local)
    # default path check: point ROOT-derived default at tmp via monkeypatch of _load_json_fresh default
    # instead, call the helper directly with the real default path relationship
    with mock.patch("requests.get", return_value=FakeResp(remote)):
        out = snapshots._load_json_fresh(
            snapshots.ROOT / "data/automation/alerts_feed.json",
            "data/automation/alerts_feed.json",
        )
    assert out == remote


def test_local_fallback_when_remote_fails(tmp_path, monkeypatch):
    _fresh(monkeypatch)
    local = tmp_path / "x.json"
    local.write_text(json.dumps({"generated_at": "local"}))
    with mock.patch("requests.get", side_effect=Exception("no net")):
        out = snapshots._load_json_fresh(local, "data/automation/x.json")
    assert out == {"generated_at": "local"}


def test_custom_path_stays_local_only(tmp_path, monkeypatch):
    _fresh(monkeypatch)
    local = tmp_path / "custom.json"
    local.write_text(json.dumps({"generated_at": "local"}))
    with mock.patch("requests.get", side_effect=AssertionError("must not fetch")):
        out = snapshots._load_json_fresh(local, "data/automation/other.json")
    assert out == {"generated_at": "local"}


def test_cache_avoids_repeat_fetches(monkeypatch):
    _fresh(monkeypatch)
    calls = {"n": 0}

    def fake_get(*a, **k):
        calls["n"] += 1
        return FakeResp({"v": 1})

    with mock.patch("requests.get", side_effect=fake_get):
        assert snapshots._fetch_repo_json("data/automation/alerts_feed.json") == {"v": 1}
        assert snapshots._fetch_repo_json("data/automation/alerts_feed.json") == {"v": 1}
    assert calls["n"] == 1


def test_status_meta_marks_github_source(monkeypatch):
    _fresh(monkeypatch)
    with mock.patch("requests.get", return_value=FakeResp({"v": 2})):
        payload, meta = snapshots._load_json_fresh_status(
            snapshots.ROOT / "data/automation/alerts_feed.json",
            "data/automation/alerts_feed.json")
    assert payload == {"v": 2}
    assert meta["source"] == "github-api"
    assert meta["checked_at"]
    assert meta["fallback_reason"] is None


def test_status_meta_marks_fallback_with_reason(monkeypatch):
    _fresh(monkeypatch)
    with mock.patch("requests.get", side_effect=Exception("down")):
        payload, meta = snapshots._load_json_fresh_status(
            snapshots.ROOT / "data/automation/alerts_feed.json",
            "data/automation/alerts_feed.json")
    assert payload is not None, "repo ships a local copy to fall back to"
    assert meta["source"] == "local-fallback"
    assert meta["fallback_reason"]


def test_status_meta_missing_when_nothing(monkeypatch):
    _fresh(monkeypatch)
    with mock.patch("requests.get", side_effect=Exception("down")):
        payload, meta = snapshots._load_json_fresh_status(
            snapshots.ROOT / "data/automation/alerts_feed.json",
            "data/automation/alerts_feed.json")
    # local file exists in repo, so fallback with reason is acceptable too
    if payload is None:
        assert meta["source"] == "missing"
    else:
        assert meta["source"] == "local-fallback"
        assert meta["fallback_reason"]


def test_report_export_remote_first_then_local(tmp_path, monkeypatch):
    _fresh(monkeypatch)
    snapshots._text_cache.clear()
    target_dir = snapshots.ROOT / "data" / "automation" / "reports"
    with mock.patch("requests.get") as get:
        get.return_value = type("R", (), {"ok": True, "text": "<html>x</html>"})()
        out = snapshots.load_report_export("AAA", "NSE", "html")
    assert out == "<html>x</html>"
    # bad format guard
    assert snapshots.load_report_export("AAA", "NSE", "exe") is None


def test_report_export_local_fallback(tmp_path, monkeypatch):
    _fresh(monkeypatch)
    snapshots._text_cache.clear()
    d = tmp_path / "reports"
    d.mkdir()
    (d / "NSE_BBB.csv").write_text("a,b\n")
    out = snapshots.load_report_export("BBB", "NSE", "csv", directory=d)
    assert out == "a,b\n"
