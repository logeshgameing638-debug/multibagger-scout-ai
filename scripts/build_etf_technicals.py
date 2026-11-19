"""Build data/etf_technicals.json: NAV-history indicators for the curated ETFs.

Free-first: fetches daily NAV history from api.mfapi.in (a free, no-key
community mirror of AMFI data). Basis is the fund's daily NAV, NOT the
exchange market price, so these indicators are informational only: no trade
entries, stop-losses or targets are derived from NAV. Market-price technical
setups for ETFs remain unavailable on free data.

Split handling: daily NAV series can contain split/bonus discontinuities
(e.g. BeES 1:10 splits). Jumps beyond +/-30% in one day are impossible for
the underlying indices, so the older segment is rescaled by the detected
factor before computing indicators. If a jump cannot be snapped to a clean
ratio, indicators for that ETF are reported as unavailable rather than
computed on a broken series.

Never raises: per-ETF failures are recorded with a reason so the last good
committed feed stays usable.
"""
from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UNIVERSE = ROOT / "data" / "etf_universe.json"
OUT = ROOT / "data" / "etf_technicals.json"
SEARCH = "https://api.mfapi.in/mf/search?q="
HISTORY = "https://api.mfapi.in/mf/"

BASIS = ("Computed on daily NAV history (source: api.mfapi.in, a free mirror "
         "of AMFI data), not exchange market price. Informational only - no "
         "trade entries, stop-losses or targets are derived from NAV. "
         "Market-price technical setups for ETFs remain unavailable on free "
         "data. Series adjusted for detected splits before indicator math.")

NICE_RATIOS = [100.0, 10.0, 7.0, 5.0, 4.0, 3.0, 2.5, 2.0, 1.5,
               1/1.5, 1/2.0, 1/2.5, 1/3.0, 1/4.0, 1/5.0, 1/7.0, 1/10.0, 1/100.0]


def fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "multibagger-scout/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def resolve_scheme_code(name: str) -> tuple[int | None, str | None]:
    try:
        res = fetch_json(SEARCH + urllib.parse.quote(name))
    except Exception:
        return None, None
    pick = None
    for it in res:
        n = it["schemeName"].lower()
        if "fof" in n or "fund of fund" in n:
            continue
        if name.lower().split(" - ")[0] in n or n in name.lower():
            pick = it
            break
    if pick is None:
        cands = [it for it in res
                 if "etf" in it["schemeName"].lower() and "fof" not in it["schemeName"].lower()]
        pick = cands[0] if cands else None
    return (pick["schemeCode"], pick["schemeName"]) if pick else (None, None)


def load_series(code: int) -> list[tuple[datetime, float]]:
    """oldest -> newest list of (date, nav)."""
    payload = fetch_json(HISTORY + str(code))
    rows = payload.get("data") or []
    series = []
    for row in rows:
        try:
            series.append((datetime.strptime(row["date"], "%d-%m-%Y"), float(row["nav"])))
        except (KeyError, ValueError):
            continue
    series.sort(key=lambda x: x[0])
    return series


def split_adjust(series: list[tuple[datetime, float]]):
    """Rescale older segments around detected split jumps. Returns
    (adjusted_series, note) or (None, reason)."""
    if len(series) < 60:
        return None, "insufficient NAV history (need 60+ sessions)"
    factor = 1.0
    adj = [(d, v) for d, v in series]
    splits = 0
    for i in range(1, len(adj)):
        prev, cur = adj[i - 1][1], adj[i][1]
        if prev <= 0:
            return None, "non-positive NAV in series"
        ratio = cur / prev
        if ratio > 1.30 or ratio < 0.70:
            snapped = None
            for r in NICE_RATIOS:
                if abs(ratio - r) / r <= 0.10:
                    snapped = r
                    break
            if snapped is None:
                return None, (f"unadjustable NAV jump {ratio:.2f}x on "
                              f"{adj[i][0].date()} - series left untouched")
            # rescale everything before i by 1/snapped cumulatively
            factor *= snapped
            adj = [(d, v / snapped) if j < i else (d, v) for j, (d, v) in enumerate(adj)]
            splits += 1
    note = f"{splits} split adjustment(s) applied" if splits else "no splits detected"
    return adj, note


def ema(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def rsi_wilder(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, period + 1):
        ch = values[i] - values[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    for i in range(period + 1, len(values)):
        ch = values[i] - values[i - 1]
        avg_g = (avg_g * (period - 1) + max(ch, 0.0)) / period
        avg_l = (avg_l * (period - 1) + max(-ch, 0.0)) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return 100 - 100 / (1 + rs)


def pct(a: float, b: float) -> float:
    return (a / b - 1.0) * 100.0


def indicators(adj: list[tuple[datetime, float]]) -> dict:
    vals = [v for _, v in adj]
    last = vals[-1]
    out = {"nav": round(last, 4), "nav_date": adj[-1][0].strftime("%Y-%m-%d")}
    e20, e50, e200 = ema(vals, 20), ema(vals, 50), ema(vals, 200)
    out["ema_20"] = round(e20, 4) if e20 is not None else None
    out["ema_50"] = round(e50, 4) if e50 is not None else None
    out["ema_200"] = round(e200, 4) if e200 is not None else None
    r = rsi_wilder(vals)
    out["rsi_14"] = round(r, 1) if r is not None else None
    if e50 is not None:
        out["trend_vs_ema50"] = "above" if last > e50 else "below"
    if e200 is not None:
        out["trend_vs_ema200"] = "above" if last > e200 else "below"
    yr = [v for d, v in adj if (adj[-1][0] - d).days <= 365]
    if yr:
        hi, lo = max(yr), min(yr)
        out["nav_52w_high"] = round(hi, 4)
        out["nav_52w_low"] = round(lo, 4)
        out["pct_from_52w_high"] = round(pct(last, hi), 2)
        out["pct_from_52w_low"] = round(pct(last, lo), 2)
    for days, key in ((30, "return_1m_pct"), (182, "return_6m_pct"), (365, "return_1y_pct")):
        past = [v for d, v in adj if (adj[-1][0] - d).days >= days]
        if past:
            out[key] = round(pct(last, past[-1]), 2)
    return out


def main() -> None:
    universe = json.loads(UNIVERSE.read_text())["etfs"]
    feed = {
        "as_of": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "api.mfapi.in (free mirror of AMFI NAV history)",
        "basis": BASIS,
        "etfs": {},
    }
    for e in universe:
        sym, name = e["symbol"], e["name"]
        code = e.get("amfi_scheme_code")
        scheme_name = None
        if not code:
            code, scheme_name = resolve_scheme_code(name)
        if not code:
            feed["etfs"][sym] = {"status": "unavailable",
                                 "reason": "no AMFI scheme code found by name search"}
            continue
        try:
            series = load_series(int(code))
            adj, note = split_adjust(series)
            if adj is None:
                feed["etfs"][sym] = {"status": "unavailable", "reason": note}
                continue
            ind = indicators(adj)
            ind.update({"status": "ok", "scheme_code": int(code),
                        "adjustment": note,
                        "sessions": len(adj)})
            feed["etfs"][sym] = ind
        except Exception as exc:  # network/parse: keep last good committed feed
            feed["etfs"][sym] = {"status": "unavailable",
                                 "reason": f"fetch/parse failed: {type(exc).__name__}"}
        time.sleep(0.4)  # polite pacing for the free community API
    ok = sum(1 for v in feed["etfs"].values() if v.get("status") == "ok")
    feed["coverage"] = f"{ok}/{len(universe)} ETFs with NAV indicators"
    OUT.write_text(json.dumps(feed, indent=2))
    print(f"wrote {OUT} ({feed['coverage']})")


if __name__ == "__main__":
    main()
