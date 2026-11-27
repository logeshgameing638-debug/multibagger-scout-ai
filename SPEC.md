# Multibagger Scout AI — Project Spec

Spec-kit-style living specification for this project (structure adapted from
github.com/github/spec-kit, no tooling or API keys required). This file is the
single source of truth for WHAT the project is and the rules every change must
follow. Any agent (Instinct project agent or human) starting work on this repo
reads this file first, then picks work from `tasks/tasks.json`.

Last updated: 2026-11-27 by Instinct. The owner approved setting up this
Task Master + Spec Kit way of working on his projects on WhatsApp 2026-11-27
(his "Mm" reply to the setup offer, wamid ...UMzM0U0NTFFNzU4QjZBQ0Q5NkFEMjA5MUE2NDgyQzcA).

## 1. Constitution (never changes without the owner's explicit approval)

1. **Free-first, ₹0 budget.** No paid APIs, no paid hosting, no mandatory API
   keys. Secrets, when any exist, live in env vars only (`.env.example`
   documents names, never values).
2. **Research only.** The app never places trades, never connects a broker,
   never touches real money. It is an analysis assistant: scores, reports,
   watchlists, alerts. The UI states this boundary where money decisions show.
3. **Honest gaps, never fabrications.** Real market sources with dates. Missing
   or unverifiable data is marked `unavailable` / `partial`, never replaced
   with sample numbers. A batch is never presented as a full-market result.
4. **Works without an LLM.** All eight research agents are deterministic.
   Optional AI adapters (Ollama / free tiers) are extras, not requirements.
5. **Personal data stays private.** Portfolio, passwords and account details
   never go to the public repo or public sites (owner's decision 2026-11-19).
6. **Data rights respected.** No republishing of third-party data without
   confirmed permission; when permission is missing, the feature pauses and
   says so (example: long-term chart expansion, paused 2026-11-20).

## 2. Product spec (what it is)

Free-first Indian stock research platform covering every NSE + BSE listed
stock (owner's correction 2026-11-18: "Not 50 stock all SEBI listed stock").

- **Eight deterministic agents:** Stock Scout, Fundamental, Technical,
  Business Quality, Valuation, Growth, Risk, News — each producing
  evidence-backed reports with missing-data notes.
- **Scoring:** fundamental, technical, data confidence and risk scores /100;
  rankings: long-term (70% fundamental + 30% technical), short-term
  (70/30 reversed), balanced (50/50).
- **Universe scanning:** full NSE equity master (~2,400) and BSE session
  universe (daily common bhavcopy, ~5,100 STK rows), ISIN-deduplicated,
  resumable batches, each stock ending complete / partial / unavailable.
- **Per-stock research:** combined fundamental + technical report; separate
  short-term and long-term trade-style views (entry zone, stop-loss,
  supported target, risk/reward, potential P/L). Owner asked for 1:5
  reward:risk; when no setup qualifies the app shows "no qualifying setup"
  instead of forcing a target.
- **Surfaces:** Streamlit dashboard (eight-floor layout), FastAPI backend
  (optional), SQLite storage, scheduled jobs, pytest suite.
- **Website sections:** Large / Mid / Small cap, Penny (< ₹10), Top 50
  research ranking, ETF section, per-stock details page.
- **Automation:** overnight scan → analysis → risk checks → ranking → saved
  reports (research automation only, never automatic trades — scoped
  2026-11-19).

## 3. Current deployments

| Surface | URL | Notes |
| --- | --- | --- |
| Repo (public) | https://github.com/logeshgameing638-debug/multibagger-scout-ai | public since 2026-11-19 |
| Streamlit app | https://multibagger-scout-ai.streamlit.app/ | owner's login required |
| Public Pages site | https://logeshgameing638-debug.github.io/multibagger-scout-ai/ | dated batch data, not live |
| Demo (sample data) | https://multibagger-scout-demo.streamlit.app/ | clearly marked sample data |
| Merged view | stock-screener website → Scout Research menu | merge of 2026-11-19 |

## 4. Data sources (all free) and their rules

| Source | Used for | Rules / honest limits |
| --- | --- | --- |
| Yahoo Finance (yfinance) | prices, statements, profile, ratios | unofficial, ~15 min delayed, gaps shown |
| NSE archives CSV | index constituents, equity master | public files; throttling handled + shown |
| BSE daily common bhavcopy | session universe | session instruments, not a full registry |
| Google News RSS | headlines | headlines only |
| TejHQ (candidate, NOT live) | NSE+BSE price history | permission email sent 2026-11-21, awaiting reply; no financial statements; offline-tested only |

## 5. Non-goals (explicitly out of scope)

- Real-money trading, broker connections, order placement of any kind.
- Paid data feeds or paid hosting.
- Presenting delayed/sample data as live.
- Public exposure of the owner's portfolio, credentials, or account details.

## 6. Working agreements for project agents

- Read this file before any change; keep it truthful when reality changes.
- Pick work from `tasks/tasks.json` (top pending by priority), update task
  status as part of the change, one commit per logical change.
- "Done" means verified live (owner's standing rule: "completed means send
  link" — a fix is reported done only after it is checked on the live site).
- The owner is zero-coding: never require him to install tools, run commands
  or hold API keys for the methodology to work; agents maintain these files.
