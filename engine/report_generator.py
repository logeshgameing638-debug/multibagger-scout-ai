"""Report generation: HTML, JSON, CSV always; PDF via reportlab when importable.

Every report contains the 17 required sections, sources and timestamps.
"""
from __future__ import annotations

import csv
import html
import json
from pathlib import Path

from config import get_settings
from database.connection import session_scope
from database.models import ResearchReport


def _pct(value) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, (int, float)) else "n/a"


def _num(value) -> str:
    return f"{value:,.2f}" if isinstance(value, (int, float)) else "n/a"


def build_report_dict(bundle: dict) -> dict:
    """The canonical 17-section report structure."""
    scores = bundle["scores"]
    valuation = bundle["valuation"]
    risk = bundle["risk"]
    business = bundle["business"]
    labels = bundle.get("labels", [])
    thesis = _build_thesis(bundle)
    return {
        "1_company_profile": {
            "symbol": bundle["symbol"], "exchange": bundle["exchange"], "name": bundle["name"],
            "sector": bundle["info"].get("sector"), "industry": bundle["info"].get("industry"),
            "market_cap": bundle["info"].get("marketCap"), "website": bundle["info"].get("website"),
        },
        "2_source_and_timestamp": {
            "generated_at": bundle["generated_at"],
            "price_note": "Yahoo Finance NSE/BSE quotes typically delayed ~15 minutes",
            "agent_statuses": bundle["agent_statuses"],
        },
        "3_financial_analysis": {
            k: v for k, v in bundle["fundamentals"].items() if k != "statements"
        },
        "4_technical_analysis": {
            "assessment": bundle["technicals"].get("assessment"),
            "daily": bundle["technicals"].get("daily"),
            "short_term_report": bundle["technicals"].get("short_term_report"),
            "long_term_report": bundle["technicals"].get("long_term_report"),
        },
        "5_business_quality": business,
        "6_valuation": valuation,
        "7_news_intelligence": bundle["news"],
        "8_risk_analysis": risk,
        "9_fundamental_score": scores["fundamental"],
        "10_technical_score": scores["technical"],
        "11_data_confidence": scores["data_confidence"],
        "12_short_term_assessment": {
            "score": scores.get("short_term"),
            "technical_view": bundle["technicals"].get("short_term_report"),
            "entry_zone": bundle["technicals"].get("entry_zone"),
            "invalidation_level": bundle["technicals"].get("invalidation_level"),
        },
        "13_long_term_assessment": {
            "score": scores.get("long_term"),
            "trend": bundle["technicals"].get("long_term_report"),
            "business_classification": business.get("classification"),
        },
        "14_investment_thesis": thesis,
        "15_thesis_invalidation": _invalidation_conditions(bundle),
        "16_missing_evidence": {
            "fundamental_gaps": bundle["fundamentals"].get("red_flags", []),
            "unassessed_governance": risk.get("unassessed_governance_items", []),
            "valuation_gaps": valuation.get("dcf_not_calculated_reason"),
            "business_unassessed": business.get("unassessed_areas", []),
        },
        "17_sources": ["yahoo_finance (prices, statements, profile)", "rss_news (headlines, unverified)"],
        "labels": labels,
        "combined_scores": {
            "long_term": scores.get("long_term"), "short_term": scores.get("short_term"),
            "balanced": scores.get("balanced"), "risk_score_higher_is_worse": scores.get("risk"),
        },
        "disclaimer": (
            "Research only. A multibagger label is a hypothesis, not a prediction. "
            "Not investment advice; no trades are placed by this software."
        ),
    }


def _build_thesis(bundle: dict) -> str:
    business = bundle["business"]
    tech = bundle["technicals"]
    scores = bundle["scores"]
    parts = [
        f"{bundle['name']} ({bundle['symbol']}) is classified as a "
        f"'{business.get('classification', 'insufficient_evidence')}' business "
        f"with a {tech.get('assessment', 'unknown')} technical trend.",
        f"Balanced research score {scores.get('balanced')}/100 "
        f"(fundamental {scores.get('fundamental')}, technical {scores.get('technical')}, "
        f"data confidence {scores.get('data_confidence')}, risk {scores.get('risk')}/100 higher=worse).",
    ]
    evidence = business.get("evidence", [])[:3]
    if evidence:
        parts.append("Supporting evidence: " + "; ".join(evidence) + ".")
    return " ".join(parts)


def _invalidation_conditions(bundle: dict) -> list[str]:
    conditions = []
    inv = bundle["technicals"].get("invalidation_level")
    if inv is not None:
        conditions.append(f"Daily close below invalidation level {inv} (2x ATR under support)")
    conditions.append("Operating cash flow turning negative in the next annual report")
    conditions.append("New critical governance or regulatory finding (currently unassessed items must be checked manually)")
    return conditions


def _write_record(company_id: int | None, fmt: str, path: Path) -> None:
    if company_id is None:
        return
    with session_scope() as session:
        session.add(ResearchReport(company_id=company_id, format=fmt, path=str(path)))


def generate_company_report(bundle: dict, company_id: int | None = None) -> dict[str, str]:
    report = build_report_dict(bundle)
    exports = get_settings().exports_dir
    stem = f"{bundle['symbol']}_{bundle['exchange']}_research"
    paths: dict[str, str] = {}

    json_path = exports / f"{stem}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    paths["json"] = str(json_path)
    _write_record(company_id, "json", json_path)

    html_path = exports / f"{stem}.html"
    html_path.write_text(_render_html(bundle, report), encoding="utf-8")
    paths["html"] = str(html_path)
    _write_record(company_id, "html", html_path)

    csv_path = exports / f"{stem}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["section", "metric", "value"])
        writer.writerow(["profile", "symbol", bundle["symbol"]])
        writer.writerow(["profile", "name", bundle["name"]])
        for name, value in bundle["scores"].items():
            writer.writerow(["scores", name, value])
        writer.writerow(["classification", "labels", ", ".join(bundle.get("labels", []))])
        for group in ("growth", "profitability", "balance_sheet", "cash_flow"):
            for metric, value in bundle["fundamentals"].get(group, {}).items():
                writer.writerow([group, metric, value])
    paths["csv"] = str(csv_path)
    _write_record(company_id, "csv", csv_path)

    try:
        pdf_path = exports / f"{stem}.pdf"
        _render_pdf(bundle, report, pdf_path)
        paths["pdf"] = str(pdf_path)
        _write_record(company_id, "pdf", pdf_path)
    except ImportError:
        paths["pdf"] = "unavailable: reportlab not installed (pip install reportlab)"
    return paths


def _render_html(bundle: dict, report: dict) -> str:
    e = html.escape
    rows = []
    for section, content in report.items():
        if section in {"labels", "disclaimer", "combined_scores"}:
            continue
        rows.append(f"<h2>{e(section)}</h2><pre>{e(json.dumps(content, indent=2, default=str))}</pre>")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{e(bundle['symbol'])} research report</title>
<style>body{{font-family:system-ui;background:#0b1220;color:#dbe4f0;max-width:960px;margin:2rem auto;padding:0 1rem}}
h1,h2{{color:#7dd3fc}} pre{{background:#111a2e;padding:1rem;border-radius:8px;overflow-x:auto;white-space:pre-wrap}}
.labels span{{background:#14532d;color:#bbf7d0;padding:2px 8px;border-radius:12px;margin-right:6px}}
.disc{{color:#fbbf24}}</style></head>
<body><h1>Multibagger Scout AI - {e(bundle['name'])} ({e(bundle['symbol'])})</h1>
<p class="labels">{' '.join(f'<span>{e(label)}</span>' for label in bundle.get('labels', []))}</p>
{''.join(rows)}
<p class="disc">{e(report['disclaimer'])}</p>
</body></html>"""


def _render_pdf(bundle: dict, report: dict, path: Path) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    c.setFont("Helvetica-Bold", 14)
    c.drawString(2 * cm, y, f"Multibagger Scout AI - {bundle['name']} ({bundle['symbol']})")
    y -= 1 * cm
    c.setFont("Helvetica", 9)
    for section, content in report.items():
        if section in {"disclaimer"}:
            continue
        for line in json.dumps({section: content}, indent=1, default=str).splitlines():
            if y < 2 * cm:
                c.showPage()
                c.setFont("Helvetica", 9)
                y = height - 2 * cm
            c.drawString(2 * cm, y, line[:110])
            y -= 0.42 * cm
    c.showPage()
    c.setFont("Helvetica-Oblique", 9)
    c.drawString(2 * cm, height - 2 * cm, report["disclaimer"])
    c.save()
