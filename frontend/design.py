"""Reference-matching design system for Multibagger Scout AI.

Dark institutional terminal look per the user's dashboard reference:
dark navy background, thin card borders, neon green bullish accents,
blue interactive elements, purple/orange analytical indicators.
All values rendered here come from real data passed in by the caller;
helpers never invent numbers.
"""
from __future__ import annotations

import html

DESIGN_CSS = """
<style>
:root {
  --bg: #060b18;
  --bg-panel: #0c1428;
  --bg-card: #101a33;
  --border: #1c2b4d;
  --green: #00d09c;
  --blue: #2f7bff;
  --purple: #a855f7;
  --orange: #f59e0b;
  --red: #ef4444;
  --text: #e6edf7;
  --muted: #8fa1bf;
}
.stApp { background-color: var(--bg); color: var(--text); }
section[data-testid="stSidebar"] { background-color: #0a1128; border-right: 1px solid var(--border); }
header[data-testid="stHeader"] { background: transparent; }
#MainMenu { visibility: hidden; }
h1, h2, h3, h4 { color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; }
.stApp, .stApp p, .stApp span, .stApp li, .stApp td, .stApp th { color: var(--text); }
.muted { color: var(--muted); }
label, .stMarkdown label, div[data-testid="stWidgetLabel"],
div[data-testid="stWidgetLabel"] p, div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label, div[data-testid="stNumberInput"] label,
div[data-testid="stMultiSelect"] label, div[data-testid="stSlider"] label,
div[data-testid="stRadio"] label, div[data-testid="stCheckbox"] label,
div[data-testid="stDateInput"] label, div[data-testid="stExpander"] summary p {
    color: #b9c6dd !important;
}
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] .stMarkdown {
    color: #b9c6dd !important;
}
.stButton > button, button[kind="primary"], button[kind="secondary"] {
    background: #14224a; color: var(--text); border: 1px solid var(--border); border-radius: 8px;
}
.stButton > button:hover { background: #1b2f63; color: #ffffff; border-color: var(--blue); }
.stDownloadButton > button { background: #14224a; color: var(--text); border: 1px solid var(--border); }
div[data-baseweb="select"] > div { background-color: var(--bg-card); color: var(--text); border-color: var(--border); }
input, textarea { color: var(--text) !important; }
div[data-testid="stDataFrame"] { background: var(--bg-card); border-radius: 8px; }
div[data-testid="stMetricValue"] { color: var(--text); }

/* tabs: pill style like the reference */
.stTabs [data-baseweb="tab-list"] { gap: 4px; background: transparent; flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] {
    background: #0e1830; border: 1px solid var(--border); border-radius: 8px;
    color: #b9c6dd; padding: 6px 14px;
}
.stTabs [aria-selected="true"] { background: var(--blue) !important; color: #fff !important; }

/* reference cards */
.mb-card {
    background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px;
    padding: 16px 18px; margin-bottom: 10px;
}
.mb-card h4 { margin: 0 0 10px 0; font-size: 1.02rem; color: var(--text); }
.mb-panel-title { display: flex; align-items: center; gap: 8px; font-weight: 600; }

/* header */
.mb-header { display: flex; align-items: center; justify-content: space-between;
    padding: 6px 2px 14px 2px; flex-wrap: wrap; gap: 10px; }
.mb-brand { display: flex; align-items: center; gap: 12px; }
.mb-brand .name { font-size: 1.25rem; font-weight: 800; letter-spacing: 0.4px; color: var(--text); }
.mb-brand .tag { color: var(--muted); font-size: 0.8rem; }
.mb-pill { border: 1px solid var(--border); border-radius: 999px; padding: 5px 14px;
    font-size: 0.82rem; color: #b9c6dd; background: var(--bg-card); white-space: nowrap; }
.mb-pill.green { background: rgba(0,208,156,0.14); border-color: rgba(0,208,156,0.5); color: var(--green); font-weight: 700; }

/* pipeline */
.mb-pipe { display: flex; align-items: flex-start; justify-content: space-between; gap: 4px; }
.mb-stage { flex: 1; text-align: center; position: relative; min-width: 0; }
.mb-stage .ico {
    width: 44px; height: 44px; margin: 0 auto 6px auto; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; font-size: 1.15rem;
    border: 2px solid var(--border); background: #0e1830; position: relative; z-index: 2;
}
.mb-stage .nm { font-size: 0.74rem; color: #b9c6dd; font-weight: 600; }
.mb-stage .stt { font-size: 0.72rem; margin-top: 2px; }
.mb-stage.done .ico { border-color: var(--green); background: rgba(0,208,156,0.15); }
.mb-stage.done .stt { color: var(--green); }
.mb-stage.running .ico { border-color: var(--blue); background: rgba(47,123,255,0.2); box-shadow: 0 0 12px rgba(47,123,255,0.55); }
.mb-stage.running .stt { color: var(--blue); }
.mb-stage.failed .ico { border-color: var(--red); background: rgba(239,68,68,0.15); }
.mb-stage.failed .stt { color: var(--red); }
.mb-stage.partial .ico { border-color: var(--orange); background: rgba(245,158,11,0.15); }
.mb-stage.partial .stt { color: var(--orange); }
.mb-stage.pending .stt { color: var(--muted); }
.mb-line { position: absolute; top: 22px; left: -50%; width: 100%; height: 2px;
    background: var(--border); z-index: 1; }
.mb-stage:first-child .mb-line { display: none; }
.mb-line.done { background: var(--green); }

/* overall score banner */
.mb-overall {
    background: linear-gradient(90deg, rgba(0,208,156,0.16), rgba(0,208,156,0.05));
    border: 1px solid rgba(0,208,156,0.45); border-radius: 10px;
    padding: 10px 16px; font-weight: 700; color: var(--green); font-size: 1.05rem;
}
.mb-overall .sub { display: block; font-weight: 400; font-size: 0.8rem; color: #b9c6dd; }
.mb-overall.warn { background: linear-gradient(90deg, rgba(245,158,11,0.16), rgba(245,158,11,0.05));
    border-color: rgba(245,158,11,0.45); color: var(--orange); }
.mb-overall.risk { background: linear-gradient(90deg, rgba(239,68,68,0.16), rgba(239,68,68,0.05));
    border-color: rgba(239,68,68,0.45); color: var(--red); }

/* snapshot rows */
.mb-kv { display: flex; justify-content: space-between; gap: 10px; padding: 6px 0; border-bottom: 1px dashed #1a2742; font-size: 0.9rem; }
.mb-kv .k { color: var(--muted); flex: 0 0 auto; }
.mb-kv .v { color: var(--text); font-weight: 600; text-align: right; overflow-wrap: anywhere; }

/* insight list */
.mb-ins { margin: 0; padding: 0; list-style: none; }
.mb-ins li { padding: 5px 0 5px 26px; position: relative; font-size: 0.9rem; }
.mb-ins li::before { content: "\\2713"; position: absolute; left: 2px; color: var(--green); font-weight: 700; }
.mb-ins li.warn::before { content: "\\26A0"; color: var(--orange); }

/* sidebar market widget */
.mb-mkt { background: rgba(0,208,156,0.08); border: 1px solid rgba(0,208,156,0.35);
    border-radius: 12px; padding: 12px 14px; margin-top: 14px; }
.mb-mkt.closed { background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.35); }
.mb-mkt.unknown { background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.35); }
.mb-mkt .status { font-weight: 700; font-size: 0.95rem; }
.mb-mkt .idx { font-size: 0.86rem; color: #b9c6dd; margin-top: 4px; }
.mb-mkt .ts { font-size: 0.72rem; color: var(--muted); margin-top: 6px; }

/* sidebar nav radio as menu */
section[data-testid="stSidebar"] div[role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    background: transparent; border-radius: 8px; padding: 8px 12px; width: 100%;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) {
    background: var(--blue);
}
section[data-testid="stSidebar"] div[role="radiogroup"] label:has(input:checked) p { color: #fff !important; font-weight: 700; }

/* price strip */
.mb-price { font-size: 1.9rem; font-weight: 800; }
.mb-up { color: var(--green); font-weight: 700; }
.mb-down { color: var(--red); font-weight: 700; }
.mb-chip { display: inline-block; border: 1px solid var(--border); border-radius: 6px;
    padding: 2px 10px; font-size: 0.78rem; color: #b9c6dd; margin-right: 6px; background: #0e1830; }
.mb-chip.blue { border-color: var(--blue); color: #7fb0ff; }

@media (max-width: 900px) {
  .mb-stage .nm { font-size: 0.62rem; }
  .mb-stage .ico { width: 34px; height: 34px; font-size: 0.95rem; }
  .mb-line { top: 17px; }
  .mb-price { font-size: 1.4rem; }
}
</style>
"""

LOGO_SVG = (
    '<svg width="42" height="42" viewBox="0 0 48 48" fill="none">'
    '<rect x="2" y="2" width="44" height="44" rx="10" fill="#0c1428" stroke="#00d09c" stroke-width="2"/>'
    '<polyline points="10,34 20,22 27,28 38,12" stroke="#00d09c" stroke-width="3.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    '<polyline points="30,12 38,12 38,20" stroke="#00d09c" stroke-width="3.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
    "</svg>"
)

ICONS = {
    "scout": "\U0001F50D", "fundamental": "\U0001F4D1", "technical": "\U0001F4C8",
    "business": "\U0001F4BC", "valuation": "\U0001F9EE", "risk": "\U0001F6E1\uFE0F",
    "news": "\U0001F4F0", "scoring": "\u2B50",
}


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def header(st, right_pills: list[str] | None = None) -> None:
    pills = "".join(f'<span class="mb-pill">{esc(p)}</span>' for p in (right_pills or []))
    st.markdown(
        f'<div class="mb-header"><div class="mb-brand">{LOGO_SVG}'
        '<div><div class="name">MULTIBAGGER SCOUT AI</div>'
        '<div class="tag">Smart Research. Smarter Investing.</div></div></div>'
        f'<div style="display:flex;gap:8px;align-items:center;">{pills}</div></div>',
        unsafe_allow_html=True,
    )


def ring_svg(score: float | None, label: str, sub: str, color: str) -> str:
    """SVG donut ring. score None renders an empty ring with n/a."""
    if score is None:
        pct, text = 0.0, "n/a"
    else:
        pct = max(0.0, min(100.0, float(score)))
        text = f"{pct:.0f}"
    r = 34
    circ = 2 * 3.14159265 * r
    dash = circ * pct / 100.0
    return (
        f'<div style="text-align:center;">'
        f'<svg width="92" height="92" viewBox="0 0 92 92">'
        f'<circle cx="46" cy="46" r="{r}" stroke="#1c2b4d" stroke-width="9" fill="none"/>'
        f'<circle cx="46" cy="46" r="{r}" stroke="{color}" stroke-width="9" fill="none"'
        f' stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 46 46)"/>'
        f'<text x="46" y="44" text-anchor="middle" fill="#e6edf7" font-size="19" font-weight="700">{text}</text>'
        f'<text x="46" y="60" text-anchor="middle" fill="#8fa1bf" font-size="10">/100</text>'
        f"</svg>"
        f'<div style="font-size:0.85rem;color:#e6edf7;font-weight:600;">{esc(label)}</div>'
        f'<div style="font-size:0.74rem;color:#8fa1bf;">{esc(sub)}</div></div>'
    )


def progress_ring_svg(pct: float) -> str:
    pct = max(0.0, min(100.0, pct))
    r = 40
    circ = 2 * 3.14159265 * r
    dash = circ * pct / 100.0
    return (
        '<div style="text-align:center;"><svg width="104" height="104" viewBox="0 0 104 104">'
        f'<circle cx="52" cy="52" r="{r}" stroke="#1c2b4d" stroke-width="10" fill="none"/>'
        f'<circle cx="52" cy="52" r="{r}" stroke="#00d09c" stroke-width="10" fill="none"'
        f' stroke-linecap="round" stroke-dasharray="{dash:.1f} {circ:.1f}" transform="rotate(-90 52 52)"/>'
        f'<text x="52" y="58" text-anchor="middle" fill="#e6edf7" font-size="20" font-weight="700">{pct:.0f}%</text>'
        "</svg><div style=\"font-size:0.8rem;color:#8fa1bf;\">Overall Progress</div></div>"
    )


STATUS_LABEL = {
    "done": "\u2713 Done",
    "running": "\u25F7 In Progress...",
    "pending": "\u23F8 Pending",
    "failed": "\u2717 Failed",
    "partial": "\u25D0 Partial",
}


def pipeline_html(stages: list[dict]) -> str:
    """stages: [{key, name, icon, status}] status in done/running/pending/failed/partial."""
    parts = []
    prev_done = True
    for i, stage in enumerate(stages):
        status = stage.get("status", "pending")
        line_cls = "mb-line done" if (i > 0 and prev_done and status == "done") else "mb-line"
        parts.append(
            f'<div class="mb-stage {status}"><div class="{line_cls}"></div>'
            f'<div class="ico">{stage.get("icon", "")}</div>'
            f'<div class="nm">{i + 1}. {esc(stage["name"])}</div>'
            f'<div class="stt">{STATUS_LABEL.get(status, status)}</div></div>'
        )
        prev_done = status == "done"
    return '<div class="mb-pipe">' + "".join(parts) + "</div>"


def kv(rows: list[tuple[str, object]]) -> str:
    return "".join(
        f'<div class="mb-kv"><span class="k">{esc(k)}</span><span class="v">{esc(v)}</span></div>'
        for k, v in rows
    )
