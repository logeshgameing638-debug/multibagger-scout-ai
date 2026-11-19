"""Scheduled automation alert checks (GitHub Actions).

Reads the committed per-stock snapshots produced by scripts/daily_update.py
and derives MARKET-DATA-ONLY alerts: score moves, stored high risk, RSI
extremes and breakout/breakdown flags. No watchlists, holdings, orders or any
user activity is read or written - the public repo only ever carries
market-derived research data.

Results are committed as data/automation/alerts_feed.json; the hosted app
reads that file and shows the feed with its run timestamps. Cadence is the
scheduled rotation cadence (roughly one batch per weekday evening IST, with
GitHub Actions delays/drops possible) - this is scheduled-batch automation,
not continuous monitoring.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT_DIR = ROOT / "data" / "snapshots"
FEED_FILE = ROOT / "data" / "automation" / "alerts_feed.json"
PREV_SCORES_FILE = ROOT / "data" / "automation" / "prev_scores.json"

IST = timezone(timedelta(hours=5, minutes=30))

SCORE_CHANGE_THRESHOLD = 10.0   # balanced-score points, matches services/alerts.py default
RISK_HIGH_THRESHOLD = 70.0      # stored risk score 0-100; >= means high stored risk
RSI_OVERBOUGHT = 70.0
RSI_OVERSOLD = 30.0
MAX_FEED_ALERTS = 200


def _now_ist() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def compute_alerts(snapshots: dict[str, dict], prev_scores: dict[str, dict],
                   now: str) -> tuple[list[dict], dict[str, dict]]:
    """Derive new alerts from snapshots vs the previous score state.

    Each alert is keyed (symbol, type, data date) so re-runs never duplicate
    an alert for the same underlying data."""
    alerts: list[dict] = []
    new_prev: dict[str, dict] = {}
    for symbol, snap in sorted(snapshots.items()):
        scores = snap.get("scores") or {}
        updated = snap.get("updated_at", "")
        classification = snap.get("classification")
        new_prev[symbol] = {
            "balanced": scores.get("balanced"),
            "classification": classification,
            "updated_at": updated,
        }
        prev = prev_scores.get(symbol) or {}
        prev_balanced = prev.get("balanced")
        balanced = scores.get("balanced")

        def add(alert_type: str, severity: str, message: str) -> None:
            alerts.append({
                "symbol": symbol,
                "type": alert_type,
                "severity": severity,
                "message": message,
                "data_date": updated,
                "detected_at": now,
            })

        if isinstance(balanced, (int, float)) and isinstance(prev_balanced, (int, float)):
            delta = balanced - prev_balanced
            if abs(delta) >= SCORE_CHANGE_THRESHOLD:
                add("score_change", "warning",
                    f"{symbol} balanced score moved {delta:+.1f} pts "
                    f"({prev_balanced:.1f} -> {balanced:.1f})")
        prev_class = prev.get("classification")
        if classification and prev_class and classification != prev_class:
            add("classification_change", "info",
                f"{symbol} classification changed {prev_class} -> {classification}")

        risk = scores.get("risk")
        if isinstance(risk, (int, float)) and risk >= RISK_HIGH_THRESHOLD:
            add("risk_high", "critical",
                f"{symbol} stored risk score {risk:.0f} >= {RISK_HIGH_THRESHOLD:.0f} (high stored risk)")

        daily = snap.get("technical_daily") or {}
        rsi = daily.get("rsi_14")
        if isinstance(rsi, (int, float)):
            if rsi >= RSI_OVERBOUGHT:
                add("rsi_overbought", "info",
                    f"{symbol} RSI(14) {rsi:.0f} >= {RSI_OVERBOUGHT:.0f} (overbought zone)")
            elif rsi <= RSI_OVERSOLD:
                add("rsi_oversold", "info",
                    f"{symbol} RSI(14) {rsi:.0f} <= {RSI_OVERSOLD:.0f} (oversold zone)")
        if daily.get("breakout"):
            add("breakout", "info",
                f"{symbol} confirmed breakout above resistance {daily.get('resistance')}")
        if daily.get("breakdown"):
            add("breakdown", "warning",
                f"{symbol} broke below support {daily.get('support')}")
    return alerts, new_prev


def run(snapshot_dir: Path = SNAPSHOT_DIR, feed_file: Path = FEED_FILE,
        prev_file: Path = PREV_SCORES_FILE) -> dict:
    snapshots: dict[str, dict] = {}
    if snapshot_dir.exists():
        for path in sorted(snapshot_dir.glob("*.json")):
            payload = _load_json(path, None)
            if isinstance(payload, dict) and payload.get("symbol"):
                snapshots[payload["symbol"]] = payload

    now = _now_ist()
    feed = _load_json(feed_file, {"generated_at": None, "alerts": [], "stats": {}})
    prev_scores = _load_json(prev_file, {})

    new_alerts, new_prev = compute_alerts(snapshots, prev_scores, now)
    existing_keys = {
        (a.get("symbol"), a.get("type"), a.get("data_date"))
        for a in feed.get("alerts", [])
    }
    fresh = [
        a for a in new_alerts
        if (a.get("symbol"), a.get("type"), a.get("data_date")) not in existing_keys
    ]
    merged = (fresh + feed.get("alerts", []))[:MAX_FEED_ALERTS]

    feed = {
        "generated_at": now,
        "alerts": merged,
        "stats": {
            "snapshots_scanned": len(snapshots),
            "new_alerts": len(fresh),
            "active_alerts": len(merged),
        },
    }
    feed_file.parent.mkdir(parents=True, exist_ok=True)
    feed_file.write_text(json.dumps(feed, indent=2, default=str))
    prev_file.write_text(json.dumps(new_prev, indent=2, default=str))
    return feed


if __name__ == "__main__":
    result = run()
    print(json.dumps(result["stats"]))
