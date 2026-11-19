# Multibagger Scout AI

Free-first Indian stock research platform (NSE + BSE). Eight deterministic
research agents, a transparent scoring engine, a dark-themed Streamlit
dashboard, a FastAPI backend, SQLite storage, scheduled jobs and automated
tests. **Research only - it never places trades.**

> A "multibagger" label produced by this software is a research hypothesis,
> not a prediction or advice. Free data can be delayed, incomplete or wrong;
> the app shows those gaps instead of hiding them.

## What you need

- Windows 10/11 (or any OS with Python)
- Python 3.10 or newer from <https://www.python.org/downloads/>
  - During install, tick **"Add python.exe to PATH"**
- An internet connection (4G is fine; a 50-stock scan downloads real data)

## Install (Windows)

1. Extract the ZIP anywhere, e.g. `Documents\multibagger_scout_ai`.
2. Double-click `scripts\setup.bat`. It will:
   - check Python, create a virtual environment, install free dependencies,
   - create `.env` from `.env.example`,
   - initialise the local database,
   - run the automated test suite.
3. Double-click `scripts\run_dashboard.bat` and open the address shown
   (usually <http://localhost:8501>).

Optional: `scripts\run_backend.bat` starts the REST API on
<http://127.0.0.1:8000> (docs at `/docs`). The dashboard does not need it.

`scripts\backup_database.bat` copies your database into `backups\`.

## Daily use

- **Stock Scout** - run a scan (NIFTY 50 / NIFTY NEXT 50 / NIFTY 100 or your
  own `SYMBOL:NSE` / `CODE:BSE` list). A 50-stock scan takes a few minutes.
- **Full-market universe** - Stock Scout can load every NSE listed equity
  (official EQ-series master, ~2,400 stocks) and, when reachable, the BSE
  scrip master (configurable `BSE_EQUITY_MASTER_URL`; failures are shown, not
  hidden). Dual-listed companies are deduplicated by ISIN. Scanning runs in
  resumable batches: every stock ends up **complete / partial / unavailable**
  and the page always shows the coverage count against the whole listed
  universe - a batch is never presented as a full-market result. A
  full-market run takes many hours by design to keep provider load bounded.
- **NSE / BSE Screeners** - search, filter and export what you scanned.
- **Fundamental / Technical / Business / Valuation / Risk / News pages** -
  per-company agent reports with evidence and missing-data notes.
- **Stock Ranking** - long-term (70% fundamental + 30% technical),
  short-term (70% technical + 30% fundamental) and balanced (50/50) scores.
- **Company Research** - full detail, candlestick chart, score explanations,
  downloadable HTML / CSV / JSON / PDF reports.
- **Multibagger Watchlist** - manual adds plus automatic adds when a company
  earns the hypothesis label.
- **Alerts / Settings / Data Source Health** - risk and score-change alerts,
  per-job scheduler toggles, backup, and live provider status.

## Data sources (all free)

| Source | Used for | Honest limits |
| --- | --- | --- |
| Yahoo Finance via yfinance | prices, statements, profile, ratios | unofficial; NSE/BSE quotes typically delayed ~15 min; occasional missing fields |
| NSE archives CSV | index constituents, equity master | public files; NSE may throttle |
| BSE site CSV | scrip master | path changes over time; configurable via `BSE_EQUITY_MASTER_URL`; failures shown on Data Source Health |
| Google News RSS | company headlines | headlines are labelled UNVERIFIED, never treated as confirmed evidence |

If a provider fails, the rest of the app keeps working and the failure stays
visible on the Data Source Health page. Delayed data is always labelled.

## What the app deliberately does NOT do

- No paid APIs, ever. No API key is required for core functionality.
- No brokerage connection and no order placement.
- No invented prices, statements, symbols, news or "fair values". When data is
  missing, scores lose points and the gap is named.
- Cross-source consistency is scored only when the same company's same-period
  values are actually compared across two independent sources. Free sources
  currently can't supply that, so the subscore reports **not checked** rather
  than pretending sources agree.
- No exchange-announcement, results-calendar or corporate-filing monitoring:
  no free source covers them reliably, so they are not claimed anywhere.
- Governance items free sources can't verify (auditor changes, related-party
  deals, promoter pledging) are marked **UNASSESSED**, not cleared.
- Synthetic test data exists only inside `tests/` and is never shown as
  market data.

## Scheduling

Settings page toggles three jobs (daily scan, watchlist monitor, news
refresh). They run through APScheduler **only while the app process is
running**. For a daily scan, leave the dashboard open or run it each evening.
On hosted free tiers (Streamlit Community Cloud) the app sleeps when nobody
visits, so these in-app jobs do **not** run there; use the rotation updater
below for hosted freshness.

## Hosted daily updates (GitHub Actions rotation)

`.github/workflows/daily_update.yml` runs `scripts/daily_update.py` every
weekday at 18:30 IST on GitHub's free tier. Each run researches one bounded
batch (default 75 stocks, max ~16 minutes) of the full NSE universe
(`data/universe_nse_part*.csv`, 2,404 equities) and commits one JSON snapshot per
stock to `data/snapshots/` plus `data/rotation_state.json`. The hosted app
reads those snapshots, so the site always shows how fresh each stock is.

Honest limits:

- This is a **rotation**, not a daily full-market scan. At ~75 stocks per
  weekday the whole universe is refreshed roughly every 6-7 weeks. Every
  stock carries its own "updated at" date and the Overview page shows
  coverage, oldest and newest data dates.
- A stock that fails is stored as `unavailable` with the error and retried
  on the next cycle; failed days are never silently presented as fresh.
- Scheduled workflows can start a few minutes late under GitHub load. If the
  free monthly Actions minutes are exhausted, runs simply stop until the next
  month (no charges - verify no payment method is attached to the account).
- If NSE/yfinance blocks GitHub's runner IPs on a given day, that day's batch
  lands as `unavailable` and the site shows the previous good dates.

## Configuration

Copy `.env.example` to `.env` (setup.bat does this). Everything has working
defaults. Optional extras:

- `OLLAMA_ENABLED=true` with a local [Ollama](https://ollama.com) install adds
  optional LLM assistance. Core agents never need it.
- `DATABASE_URL` can point at PostgreSQL later (default is SQLite).
- `NEWS_RSS_FEEDS` adds market-wide RSS feeds.

## Tests

```
python -m pytest tests -q
```

64 tests cover symbol validation, OHLCV validation, indicator math (EMA, RSI,
MACD, ADX, ATR, Bollinger), financial ratios, missing-value behaviour,
scoring budgets, risk classification, ranking, database constraints, API
endpoints, and report/CSV generation. All use synthetic fixtures.

## Project layout

```
app.py                  Streamlit dashboard (17 pages)
backend.py              FastAPI server
config/                 env-driven settings
frontend/               theme, components, pages
backend/                FastAPI app + pydantic schemas
agents/                 the eight specialist agents
engine/                 orchestrator, ranking, report generator
data/                   connectors, validation, cache
indicators/             EMA/SMA/RSI/MACD/ADX/ATR/Bollinger/VWAP
database/               models, connection, migrations
services/               scanner, watchlist, alerts, scheduler, backup
tests/                  pytest suite (synthetic data only)
exports/                generated reports
scripts/                Windows .bat helpers
```

## Troubleshooting

- **"Python not found"** - reinstall Python and tick "Add python.exe to PATH".
- **pip install fails** - check internet, then re-run `scripts\setup.bat`.
- **A provider shows "down"** - open Data Source Health and re-check; Yahoo or
  NSE occasionally throttle. Wait a few minutes and retry.
- **No data for a symbol** - smaller/illiquid names sometimes lack Yahoo
  coverage; the app says so rather than guessing.
- **Port already in use** - close the other dashboard/backend window first.
- **Antivirus flags the .bat** - the scripts only run python/pip commands;
  you can read them in Notepad.

## Security notes

- No secrets in code; configuration via environment variables.
- The database stays on your machine; the backend binds to 127.0.0.1.
- Add authentication and rate limiting before any non-local deployment.
