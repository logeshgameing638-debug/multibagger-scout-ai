"""Dark navy institutional theme for the dashboard."""

DARK_CSS = """
<style>
.stApp { background-color: #0b1220; color: #dbe4f0; }
section[data-testid="stSidebar"] { background-color: #0e1729; }
h1, h2, h3 { color: #7dd3fc; font-family: 'Segoe UI', system-ui, sans-serif; }
div[data-testid="stMetricValue"] { color: #e2e8f0; }
.bullish { color: #22c55e; font-weight: 600; }
.bearish { color: #ef4444; font-weight: 600; }
.warning { color: #f59e0b; font-weight: 600; }
.muted { color: #94a3b8; }
.score-card {
    background: #111a2e; border: 1px solid #1e2b45; border-radius: 10px;
    padding: 14px; text-align: center;
}
.score-card .value { font-size: 1.8rem; font-weight: 700; }
.score-card .label { color: #94a3b8; font-size: 0.85rem; }
div[data-testid="stDataFrame"] { background: #111a2e; border-radius: 8px; }
/* contrast fixes: labels, widgets, header, buttons */
header[data-testid="stHeader"] { background: #0b1220; }
.stApp, .stApp p, .stApp span, .stApp li, .stApp td, .stApp th { color: #dbe4f0; }
label, .stMarkdown label, div[data-testid="stWidgetLabel"],
div[data-testid="stWidgetLabel"] p, div[data-testid="stSelectbox"] label,
div[data-testid="stTextInput"] label, div[data-testid="stNumberInput"] label,
div[data-testid="stMultiSelect"] label, div[data-testid="stSlider"] label,
div[data-testid="stRadio"] label, div[data-testid="stCheckbox"] label,
div[data-testid="stDateInput"] label, div[data-testid="stExpander"] summary p {
    color: #cbd5e1 !important;
}
section[data-testid="stSidebar"] label, section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] .stMarkdown {
    color: #cbd5e1 !important;
}
.stButton > button, button[kind="primary"], button[kind="secondary"] {
    background: #1e2b45; color: #e2e8f0; border: 1px solid #334866;
}
.stButton > button:hover { background: #263758; color: #ffffff; }
.stDownloadButton > button { background: #1e2b45; color: #e2e8f0; border: 1px solid #334866; }
div[data-baseweb="select"] > div { background-color: #111a2e; color: #dbe4f0; }
input, textarea { color: #dbe4f0 !important; }
@media (max-width: 640px) {
  .score-card { padding: 10px; }
  .score-card .value { font-size: 1.3rem; }
}
</style>
"""

BULL = '<span class="bullish">{}</span>'
BEAR = '<span class="bearish">{}</span>'
WARN = '<span class="warning">{}</span>'


def apply_theme(st) -> None:
    st.set_page_config(page_title="Multibagger Scout AI", layout="wide", page_icon="📈")
    from frontend import design
    st.markdown(DARK_CSS + design.DESIGN_CSS, unsafe_allow_html=True)


def colored(value: str) -> str:
    text = str(value).lower()
    if any(w in text for w in ("bullish", "strong", "positive", "low", "breakout")):
        return BULL.format(value)
    if any(w in text for w in ("bearish", "weak", "negative", "high", "critical", "breakdown")):
        return BEAR.format(value)
    if any(w in text for w in ("moderate", "sideways", "unassessed", "insufficient", "partial")):
        return WARN.format(value)
    return str(value)
