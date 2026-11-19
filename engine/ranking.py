"""Ranking: combines scores per the spec's weighting and assigns labels.

long_term  = fundamental * 0.7 + technical * 0.3
short_term = technical  * 0.7 + fundamental * 0.3
balanced   = 0.5 * long_term + 0.5 * short_term  (== 0.5F + 0.5T)
"""
from __future__ import annotations


def combine_scores(fundamental: float | None, technical: float | None) -> dict:
    if fundamental is None and technical is None:
        return {"long_term": None, "short_term": None, "balanced": None}
    f = fundamental if fundamental is not None else 0.0
    t = technical if technical is not None else 0.0
    long_term = f * 0.7 + t * 0.3
    short_term = t * 0.7 + f * 0.3
    return {
        "long_term": round(long_term, 1),
        "short_term": round(short_term, 1),
        "balanced": round(0.5 * long_term + 0.5 * short_term, 1),
        "weights": {"long_term": "0.7F+0.3T", "short_term": "0.7T+0.3F", "balanced": "0.5L+0.5S"},
    }


def classify(
    balanced: float | None,
    fundamental: float | None,
    technical: float | None,
    risk_score: float | None,
    risk_classification: str | None,
    data_confidence: float | None,
    business_classification: str | None,
    margin_of_safety: float | None,
) -> list[str]:
    """A candidate can carry several labels. Multibagger is a research
    hypothesis, never a guaranteed outcome."""
    labels: list[str] = []
    if data_confidence is not None and data_confidence < 40:
        labels.append("insufficient_evidence")
    if risk_classification in {"HIGH", "CRITICAL"} or (risk_score or 0) >= 50:
        labels.append("high_risk")
    if business_classification == "strong" and (fundamental or 0) >= 65:
        labels.append("high_quality_business")
    if margin_of_safety is not None and margin_of_safety >= 0.25:
        labels.append("attractive_valuation")
    if (technical or 0) >= 65:
        labels.append("strong_technical_trend")
    if (
        "high_quality_business" in labels
        and (technical or 0) >= 55
        and "high_risk" not in labels
        and "insufficient_evidence" not in labels
    ):
        labels.append("potential_multibagger_hypothesis")
    if not labels:
        labels.append("neutral")
    return labels


def rank_candidates(scored: list[dict], key: str = "balanced") -> list[dict]:
    """scored: list of dicts containing at least {symbol, scores...}.
    Returns the list sorted by the chosen combined score, None scores last."""
    return sorted(
        scored,
        key=lambda row: (row.get(key) is None, -(row.get(key) or 0)),
    )
