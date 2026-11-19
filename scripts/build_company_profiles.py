"""Build data/company_profiles.json: written business descriptions and
per-period results for the companies the site already surfaces.

Free-first source: screener.in company pages (public HTML, no API key).
Every entry carries its source URL and fetch date. Missing or unparsable
data is recorded as unavailable with a reason - never zero-filled, never
invented. Bounded per run (default 25 symbols, ranked order) so the
scheduled rotation stays inside its time budget; coverage grows run by run.
Never raises.
"""
from __future__ import annotations

import json
import re
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RANKING = ROOT / "data" / "automation" / "ranking_feed.json"
OUT = ROOT / "data" / "automation" / "company_profiles.json"
IST = timezone(timedelta(hours=5, minutes=30))
SOURCE = "screener.in company pages (public HTML)"
MAX_PERIODS = 8


def fetch(url: str) -> str | None:
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            if resp.status != 200:
                return None
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def clean(text: str) -> str:
    return unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text))).strip()


def num(text: str) -> float | None:
    t = text.replace(",", "").strip()
    if t in ("", "-"):
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_results(section_html: str) -> list[dict]:
    heads = [clean(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", section_html, re.S)]
    periods = [h for h in heads if re.match(r"^[A-Z][a-z]{2} \d{4}$", h)]
    rows = {}
    for m in re.finditer(r'<td class="text"[^>]*>(.*?)</td>(.*?)</tr>', section_html, re.S):
        label = clean(m.group(1)).replace("\xa0", " ").rstrip(" +")
        vals = [num(v) for v in re.findall(r"<td[^>]*>\s*([\d,\.\-]+)\s*</td>", m.group(2))]
        rows[label.lower()] = vals
    out = []
    n = len(periods)
    sales, profit = rows.get("sales", []), rows.get("net profit", [])
    for i, per in enumerate(periods):
        out.append({
            "period": per,
            "revenue_cr": sales[i] if i < len(sales) else None,
            "net_profit_cr": profit[i] if i < len(profit) else None,
        })
    return out[-MAX_PERIODS:] if n else out


def profile_symbol(symbol: str) -> dict:
    for suffix in ("consolidated/", ""):
        url = f"https://www.screener.in/company/{symbol}/{suffix}"
        html = fetch(url)
        if html:
            break
        url = None
    if not url:
        return {"status": "unavailable", "reason": "no screener.in company page found"}
    prof: dict = {"status": "ok", "source_url": url,
                  "consolidated": url.endswith("consolidated/")}
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.S)
    if h1:
        prof["name"] = clean(h1.group(1))
    about = re.search(r'id="company-info".*?<p[^>]*>(.*?)</p>', html, re.S)
    prof["description"] = clean(about.group(1)) if about else None
    q = re.search(r'<section id="quarters".*?</section>', html, re.S)
    prof["quarterly"] = parse_results(q.group(0)) if q else []
    a = re.search(r'<section id="profit-loss".*?</section>', html, re.S)
    prof["annual"] = parse_results(a.group(0)) if a else []
    if not prof["description"] and not prof["quarterly"] and not prof["annual"]:
        return {"status": "unavailable", "reason": "page found but no description or results parsed"}
    return prof


def ranked_symbols(limit: int, existing: dict) -> list[str]:
    """Stale-priority rotation: never-profiled ranked symbols first (rank
    order), then the stalest fetched_at, so coverage grows across runs and
    old entries refresh instead of always re-fetching the same first batch.
    """
    try:
        feed = json.loads(RANKING.read_text())
    except Exception:
        return []
    rows = feed.get("ranked") or feed.get("top") or []
    ranked = []
    for r in rows:
        sym = (r.get("symbol") if isinstance(r, dict) else None) or (r if isinstance(r, str) else None)
        if sym and re.match(r"^[A-Z0-9&\-]{2,20}$", sym):
            ranked.append(sym)
    fresh, stale = [], []
    for sym in ranked:
        prev = existing.get(sym)
        ts = (prev or {}).get("fetched_at")
        try:
            dt = datetime.strptime(ts, "%Y-%m-%d %H:%M IST") if ts else None
        except ValueError:
            dt = None
        (stale if dt else fresh).append((dt or datetime.min, sym))
    fresh_syms = [sym for _, sym in fresh]
    stale.sort(key=lambda t: t[0])
    ordered = fresh_syms + [sym for _, sym in stale]
    return ordered[:limit]


def main() -> None:
    import os
    limit = int(os.environ.get("MB_PROFILE_LIMIT", "25"))
    existing = {}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text()).get("profiles", {})
        except Exception:
            existing = {}
    feed = {
        "as_of": datetime.now(IST).strftime("%Y-%m-%d %H:%M IST"),
        "source": SOURCE,
        "basis": ("Written descriptions and per-period results as published on "
                  "the source page on the fetch date; figures are company-"
                  "reported (Rs crore), not independently audited by us."),
        "profiles": dict(existing),
    }
    symbols = ranked_symbols(limit, feed["profiles"])
    done = 0
    for sym in symbols:
        prof = profile_symbol(sym)
        prof["fetched_at"] = feed["as_of"]
        feed["profiles"][sym] = prof
        done += 1
        time.sleep(1.0)  # polite pacing on a free public site
    ok = sum(1 for v in feed["profiles"].values() if v.get("status") == "ok")
    feed["coverage"] = f"{ok}/{len(feed['profiles'])} profiled companies (batch of {done} this run)"
    OUT.write_text(json.dumps(feed, indent=1))
    print(json.dumps({"written": str(OUT), "coverage": feed["coverage"]}))


if __name__ == "__main__":
    main()
