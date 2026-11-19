"""Market status and index levels for the sidebar widget.

Honesty rules (per master spec): never show OPEN when it cannot be verified.
Status comes from the IST clock against NSE trading hours plus a live quote
check; when the quote fetch fails the widget says so instead of guessing.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))

NSE_OPEN = (9, 15)
NSE_CLOSE = (15, 30)


def _within_hours(now: datetime) -> bool:
    if now.weekday() >= 5:  # Sat/Sun
        return False
    minutes = now.hour * 60 + now.minute
    return NSE_OPEN[0] * 60 + NSE_OPEN[1] <= minutes < NSE_CLOSE[0] * 60 + NSE_CLOSE[1]


def index_levels() -> dict:
    """Latest NIFTY 50 / SENSEX levels via the free yfinance connector.

    Returns {label: {"last": float|None, "change": float|None, "change_pct": float|None,
                     "as_of": str|None, "ok": bool}}.
    Never fabricates: values stay None when the fetch fails.
    """
    out: dict[str, dict] = {}
    try:
        import yfinance as yf
    except ImportError:
        return {"NIFTY 50": {"ok": False}, "SENSEX": {"ok": False}}
    for label, ticker in (("NIFTY 50", "^NSEI"), ("SENSEX", "^BSESN")):
        entry = {"last": None, "change": None, "change_pct": None, "as_of": None, "ok": False}
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d")
            if not hist.empty:
                last_close = float(hist["Close"].iloc[-1])
                entry["last"] = last_close
                entry["as_of"] = hist.index[-1].strftime("%d %b %Y")
                if len(hist) >= 2:
                    prev = float(hist["Close"].iloc[-2])
                    entry["change"] = last_close - prev
                    entry["change_pct"] = (last_close - prev) / prev * 100 if prev else None
                entry["ok"] = True
        except Exception:
            pass
        out[label] = entry
    return out


def market_status(levels: dict | None = None, now: datetime | None = None) -> dict:
    """Open/Closed/Unverified with the reason shown in the widget."""
    now = now or datetime.now(IST)
    levels = levels or {}
    within = _within_hours(now)
    quote_ok = any(v.get("ok") for v in levels.values())
    as_of = next((v.get("as_of") for v in levels.values() if v.get("as_of")), None)
    today = now.strftime("%d %b %Y")

    if within and quote_ok:
        status, cls, note = "Open", "", "per IST market hours; index data as of " + (as_of or "n/a")
    elif within and not quote_ok:
        status, cls, note = "Unverified", "unknown", "IST clock says market hours, but the live index feed could not be checked"
    elif not within and quote_ok:
        status, cls, note = "Closed", "closed", "outside IST market hours; last close " + (as_of or "n/a")
    else:
        status, cls, note = "Closed (unverified)", "unknown", "outside IST market hours; index feed unchecked"
    return {"status": status, "class": cls, "note": note, "levels": levels, "now": now}


def render_sidebar_widget(st, levels: dict, status: dict) -> None:
    cls = status["class"]
    rows = []
    for label, entry in status["levels"].items():
        if entry.get("ok") and entry.get("last") is not None:
            chg = entry.get("change")
            pct = entry.get("change_pct")
            arrow = "\u25B2" if (chg or 0) >= 0 else "\u25BC"
            color = "#00d09c" if (chg or 0) >= 0 else "#ef4444"
            chg_txt = ""
            if chg is not None and pct is not None:
                chg_txt = f' <span style="color:{color};">{arrow} {chg:+,.2f} ({pct:+.2f}%)</span>'
            rows.append(f'<div class="idx">{label} {entry["last"]:,.2f}{chg_txt}</div>')
        else:
            rows.append(f'<div class="idx">{label} <span class="muted">unavailable</span></div>')
    st.markdown(
        f'<div class="mb-mkt {cls}"><div class="status">\U0001F4E1 Market Status: {status["status"]}</div>'
        + "".join(rows)
        + f'<div class="ts">{status["note"]}. Now {status["now"].strftime("%d %b %Y, %H:%M IST")}. Quotes may be delayed.</div></div>',
        unsafe_allow_html=True,
    )
