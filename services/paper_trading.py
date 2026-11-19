"""Floor 04/06: paper trading and paper portfolio.

Everything here is SIMULATED: orders never leave the app, fills are computed
from the latest free price feed (which may be delayed), and the cash balance
is virtual. No broker integration exists and none is implied.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select

from database.connection import session_scope
from database.models import PaperOrder, Setting

DEFAULT_VIRTUAL_CASH = 1_000_000.0
CASH_KEY = "paper_cash_balance"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def virtual_cash() -> float:
    with session_scope() as session:
        row = session.get(Setting, CASH_KEY)
        if row is None:
            session.add(Setting(key=CASH_KEY, value=str(DEFAULT_VIRTUAL_CASH)))
            return DEFAULT_VIRTUAL_CASH
        return float(row.value or DEFAULT_VIRTUAL_CASH)


def _set_cash(value: float) -> None:
    with session_scope() as session:
        row = session.get(Setting, CASH_KEY)
        if row is None:
            session.add(Setting(key=CASH_KEY, value=str(value)))
        else:
            row.value = str(value)


def _latest_price(symbol: str, exchange: str) -> tuple[float | None, str]:
    """Latest close from the free feed. Returns (price, as_of) or (None, error)."""
    from data.connectors import default_registry

    yf = default_registry().get("yahoo_finance")
    result = yf.get_history(symbol, exchange, period="5d", interval="1d")
    if not result.ok or result.data["frame"].empty:
        return None, result.error or "no price data from free feed"
    frame = result.data["frame"]
    return float(frame["close"].iloc[-1]), str(frame.index[-1])[:10]


def place_order(symbol: str, exchange: str, side: str, qty: int,
                stop_loss: float | None = None, target: float | None = None,
                note: str = "") -> dict:
    """Simulated market order: fills immediately at the latest free-feed close."""
    symbol = symbol.strip().upper()
    exchange = exchange.upper()
    side = side.upper()
    if side not in {"BUY", "SELL"}:
        return {"ok": False, "error": "side must be BUY or SELL"}
    if qty <= 0:
        return {"ok": False, "error": "qty must be positive"}
    price, as_of = _latest_price(symbol, exchange)
    if price is None:
        return {"ok": False, "error": f"cannot simulate fill: {as_of}"}

    if side == "BUY":
        if stop_loss is not None and stop_loss >= price:
            return {"ok": False,
                    "error": f"invalid stop-loss {stop_loss:,.2f}: for a BUY it must be "
                             f"below the fill price {price:,.2f}"}
        if target is not None and target <= price:
            return {"ok": False,
                    "error": f"invalid target {target:,.2f}: for a BUY it must be above "
                             f"the fill price {price:,.2f}"}
    if side == "SELL" and (stop_loss is not None or target is not None):
        return {"ok": False,
                "error": "stop-loss/target only apply to BUY entries; a SELL closes "
                         "the simulated position"}

    cash = virtual_cash()
    cost = price * qty
    if side == "BUY" and cost > cash:
        return {"ok": False, "error": f"insufficient virtual cash (need {cost:,.0f}, have {cash:,.0f})"}
    if side == "SELL":
        held = positions().get((symbol, exchange), {}).get("qty", 0)
        if qty > held:
            return {"ok": False, "error": f"only {held} simulated shares held"}

    from services import paper_risk
    gate = paper_risk.evaluate_order(symbol, exchange, side, qty, price,
                                     stop_loss, cash, invested=_invested())
    if not gate["approved"]:
        with session_scope() as session:
            session.add(PaperOrder(
                symbol=symbol, exchange=exchange, side=side, qty=qty,
                status="rejected", fill_price=None,
                stop_loss=stop_loss, target=target,
                note=note[:500], risk_status="rejected",
                risk_reasons=" | ".join(gate["reasons"])[:1000]))
        return {"ok": False, "gate": gate,
                "error": "REJECTED by the automated risk gate: "
                         + "; ".join(gate["reasons"])}

    with session_scope() as session:
        order = PaperOrder(
            symbol=symbol, exchange=exchange, side=side, qty=qty,
            status="filled", fill_price=price,
            stop_loss=stop_loss, target=target, note=note[:500],
            risk_status=gate["status"],
            risk_reasons=" | ".join(gate["reasons"] + gate["warnings"])[:1000],
            filled_at=_utcnow(),
        )
        session.add(order)
        session.flush()
        order_id = order.id
    _set_cash(cash - cost if side == "BUY" else cash + cost)
    return {"ok": True, "order_id": order_id, "fill_price": price,
            "price_as_of": as_of, "simulated": True, "gate": gate}


def _invested() -> float:
    """Cost basis of open simulated positions (for gate exposure math)."""
    return sum(pos["cost"] for pos in positions().values())


def positions() -> dict[tuple[str, str], dict]:
    """Net simulated holdings from filled orders."""
    with session_scope() as session:
        rows = session.scalars(
            select(PaperOrder).where(PaperOrder.status == "filled")
            .order_by(PaperOrder.filled_at)
        ).all()
    book: dict[tuple[str, str], dict] = {}
    for order in rows:
        key = (order.symbol, order.exchange)
        pos = book.setdefault(key, {"qty": 0, "cost": 0.0,
                                    "stop_loss": order.stop_loss, "target": order.target})
        signed = order.qty if order.side == "BUY" else -order.qty
        if order.side == "BUY":
            pos["cost"] += order.fill_price * order.qty
        else:
            if pos["qty"] > 0:
                pos["cost"] -= (pos["cost"] / pos["qty"]) * min(order.qty, pos["qty"])
        pos["qty"] += signed
        if order.stop_loss:
            pos["stop_loss"] = order.stop_loss
        if order.target:
            pos["target"] = order.target
    return {key: pos for key, pos in book.items() if pos["qty"] > 0}


def portfolio_summary() -> dict:
    """Holdings with latest prices, unrealised/realised P&L, virtual cash."""
    book = positions()
    holdings = []
    invested = unrealised = 0.0
    for (symbol, exchange), pos in sorted(book.items()):
        price, as_of = _latest_price(symbol, exchange)
        avg = pos["cost"] / pos["qty"] if pos["qty"] else 0.0
        value = (price or avg) * pos["qty"]
        pnl = ((price or avg) - avg) * pos["qty"]
        invested += pos["cost"]
        unrealised += pnl
        holdings.append({
            "symbol": symbol, "exchange": exchange, "qty": pos["qty"],
            "avg_cost": round(avg, 2), "last_price": price, "price_as_of": as_of,
            "value": round(value, 2), "unrealised_pnl": round(pnl, 2),
            "stop_loss": pos["stop_loss"], "target": pos["target"],
        })
    return {"cash": round(virtual_cash(), 2), "invested": round(invested, 2),
            "unrealised_pnl": round(unrealised, 2), "holdings": holdings,
            "simulated": True}


def trade_history(limit: int = 50) -> list[dict]:
    with session_scope() as session:
        rows = session.scalars(
            select(PaperOrder).order_by(PaperOrder.created_at.desc()).limit(limit)
        ).all()
    return [{"id": r.id, "symbol": r.symbol, "exchange": r.exchange, "side": r.side,
             "qty": r.qty, "status": r.status, "fill_price": r.fill_price,
             "stop_loss": r.stop_loss, "target": r.target,
             "created_at": str(r.created_at)[:16], "filled_at": str(r.filled_at)[:16] if r.filled_at else None,
             "risk_status": r.risk_status, "risk_reasons": r.risk_reasons,
             "note": r.note} for r in rows]


def reset_paper_account() -> dict:
    """Wipe all SIMULATED paper orders and restore the starting virtual cash.

    Used to hand back a clean paper account (e.g. after test/demo activity).
    Paper trading only - no real orders exist anywhere in the app.
    """
    with session_scope() as session:
        deleted = session.query(PaperOrder).delete()
        row = session.get(Setting, CASH_KEY)
        if row is None:
            session.add(Setting(key=CASH_KEY, value=str(DEFAULT_VIRTUAL_CASH)))
        else:
            row.value = str(DEFAULT_VIRTUAL_CASH)
    return {"deleted_orders": deleted, "cash": DEFAULT_VIRTUAL_CASH}
