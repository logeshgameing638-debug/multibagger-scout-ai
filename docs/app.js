/* Multibagger Scout AI - static research website.
   Reads the committed automation feeds (JSON) written by the scheduled
   research runs. No build step, no backend: the repo is the durable store. */
"use strict";

const REPO = "logeshgameing638-debug/multibagger-scout-ai";
const BRANCH = "main";
const RAW = `https://raw.githubusercontent.com/${REPO}/${BRANCH}`;
const FEEDS = {
  alerts: `${RAW}/data/automation/alerts_feed.json`,
  ranking: `${RAW}/data/automation/ranking_feed.json`,
  manifest: `${RAW}/data/automation/reports/manifest.json`,
  rotation: `${RAW}/data/rotation_state.json`,
  capSections: `${RAW}/data/automation/cap_sections.json`,
};
const UNIVERSE_CSVS = [1, 2, 3].map(i => `${RAW}/data/universe_nse_part${i}.csv`);
const BSE_UNIVERSE_CSV = `${RAW}/data/universe_bse.csv`;

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtScore(v) {
  if (v == null || v === "") return "n/a";
  const n = Number(v);
  return Number.isFinite(n) ? `${Math.round(n)}/100` : "n/a";
}

function fmtPct(v) {
  if (v == null || v === "") return "n/a";
  const n = Number(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "n/a";
}

function fmtNum(v) {
  if (v == null || v === "") return "n/a";
  const n = Number(v);
  if (!Number.isFinite(n)) return "n/a";
  if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(1)} Cr`;
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function fmtRupee(v) {
  if (v == null || v === "") return "n/a";
  const n = Number(v);
  return Number.isFinite(n) ? `\u20B9${n.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : esc(v);
}

function fmtEntryZone(ez) {
  if (!ez) return "";
  if (typeof ez === "object") {
    const parts = [];
    if (ez.low != null && ez.high != null) parts.push(`${fmtRupee(ez.low)} - ${fmtRupee(ez.high)}`);
    else if (ez.low != null) parts.push(`from ${fmtRupee(ez.low)}`);
    if (ez.basis) parts.push(`(${esc(ez.basis)})`);
    return parts.join(" ");
  }
  return esc(ez);
}

async function fetchJson(url) {
  const resp = await fetch(url, { cache: "no-store" });
  if (!resp.ok) throw new Error(`HTTP ${resp.status} for ${url}`);
  return resp.json();
}

function setMeta(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function renderManifest(manifest) {
  setMeta("reports-meta",
    `Reports generated ${manifest.generated_at || "unknown"} by the scheduled automation run ` +
    `(market-derived research only; not continuous monitoring). ` +
    `A generated status means the run completed; each report names its own missing evidence.`);
  const rows = manifest.reports || [];
  const head = document.querySelector("#reports-table thead");
  const body = document.querySelector("#reports-table tbody");
  head.innerHTML = "<tr><th>Symbol</th><th>Exchange</th><th>Status</th><th>Report</th></tr>";
  body.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    const ok = ["success", "partial"].includes(r.status) && r.file;
    tr.className = ok ? "clickable" : "";
    tr.innerHTML =
      `<td><strong>${esc(r.symbol)}</strong></td>` +
      `<td><span class="badge exchange">${esc(r.exchange || "NSE")}</span></td>` +
      `<td><span class="badge ${esc(r.status)}">${r.status === "success" ? "generated" : esc(r.status)}</span></td>` +
      `<td>${ok ? "Open narrative report" : esc(r.note || r.error || "unavailable")}</td>`;
    if (ok) tr.addEventListener("click", () => openReport(r));
    body.appendChild(tr);
  }
}

function renderRanking(feed) {
  setMeta("ranking-meta",
    `Ranked ${feed.ranked_count || 0} of ${feed.universe_size || "?"} universe stocks ` +
    `(${feed.excluded_count || 0} unavailable/excluded). Feed generated ${feed.generated_at || "unknown"}; ` +
    `each stock keeps its own data date. Scheduled batch research, not continuous monitoring.`);
  const head = document.querySelector("#ranking-table thead");
  const body = document.querySelector("#ranking-table tbody");
  head.innerHTML = "<tr><th>#</th><th>Symbol</th><th>Exch</th><th>Balanced</th><th>Fund.</th><th>Tech.</th><th>Confidence</th><th>Verdict</th><th>Data date</th></tr>";
  body.innerHTML = "";
  (feed.top || []).forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${i + 1}</td><td><strong>${esc(r.symbol)}</strong></td>` +
      `<td>${esc(r.exchange || "NSE")}</td>` +
      `<td>${fmtScore(r.balanced)}</td><td>${fmtScore(r.fundamental)}</td>` +
      `<td>${fmtScore(r.technical)}</td><td>${fmtScore(r.data_confidence)}</td>` +
      `<td>${esc(r.verdict || r.classification || "")}</td>` +
      `<td>${esc(r.data_date || "")}</td>`;
    body.appendChild(tr);
  });
}

function renderAlerts(feed) {
  const stats = feed.stats || {};
  setMeta("alerts-meta",
    `Last automation run ${feed.generated_at || "unknown"} - scanned ${stats.snapshots_scanned || 0} ` +
    `universe snapshots, ${stats.new_alerts || 0} new alerts this run. Market-derived research only.`);
  const head = document.querySelector("#alerts-table thead");
  const body = document.querySelector("#alerts-table tbody");
  head.innerHTML = "<tr><th>Symbol</th><th>Type</th><th>Severity</th><th>Detail</th><th>Data date</th></tr>";
  body.innerHTML = "";
  for (const a of feed.alerts || []) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td><strong>${esc(a.symbol)}</strong></td><td>${esc(a.type)}</td>` +
      `<td>${esc(a.severity)}</td><td>${esc(a.detail || a.message || "")}</td>` +
      `<td>${esc(a.data_date || "")}</td>`;
    body.appendChild(tr);
  }
}

function kvTable(obj, fmt) {
  const rows = Object.entries(obj || {})
    .map(([k, v]) => `<tr><td>${esc(k.replace(/_/g, " "))}</td><td>${fmt(v)}</td></tr>`)
    .join("");
  return rows ? `<table class="kv"><tbody>${rows}</tbody></table>` : "";
}


function conclusionHtml(r, risk, quality, ta) {
  const combined = r.combined_scores || {};
  const daily = (ta || {}).daily || {};
  const unassessed = (risk.unassessed_governance_items || []).length;
  const missing = r["16_missing_evidence"] || {};
  const gapCount = Object.values(missing).reduce((n, v) => n + (Array.isArray(v) ? v.length : (v ? 1 : 0)), 0);
  return `<h4>Overall research conclusion</h4><p>` +
    `Fundamental research scores ${fmtScore(r["9_fundamental_score"])} and rates the business '${esc(quality.classification || "n/a")}'. ` +
    `Technical research scores ${fmtScore(r["10_technical_score"])} with a ${esc((ta || {}).assessment || daily.trend || "n/a")} daily assessment` +
    `${daily.trend_strength ? ` (${esc(daily.trend_strength)} trend)` : ""}. ` +
    `Combined balanced research score: ${fmtScore(combined.balanced)} (short term ${fmtScore(combined.short_term)}, long term ${fmtScore(combined.long_term)}), ` +
    `on ${fmtScore(r["11_data_confidence"])} data confidence. Quantitative risk: ${esc(risk.classification || "n/a")}` +
    `${unassessed ? `, with ${unassessed} governance items not assessed by the free feeds` : ""}` +
    `${gapCount ? `; ${gapCount} evidence gaps are listed under Missing evidence below` : "; no evidence gaps recorded"}. ` +
    `This is combined fundamental-plus-technical research, not a buy or sell recommendation.</p>`;
}

function shortSetupHtml(short, daily, priceDate) {
  const ez = short.entry_zone || {};
  const tv = short.technical_view || {};
  const stop = Number(short.invalidation_level);
  const bearish = /bearish/i.test(tv.trend || "") || tv.breakdown === true;
  const close = daily && Number(daily.last_close);
  const closeLine = Number.isFinite(close)
    ? `<p>Stored close: ${fmtRupee(close)}${priceDate ? ` (as of the research run ${esc(priceDate)}; Yahoo quote, typically delayed ~15 min)` : ""}.</p>` : "";
  const reasons = [];
  if (bearish) reasons.push(`stored short-term trend is ${tv.trend || "bearish"}`);
  if (ez.low == null || ez.high == null) reasons.push("no stored entry range");
  if (!Number.isFinite(stop)) reasons.push("no numeric stop-loss stored");
  if (!reasons.length && stop >= ez.low) reasons.push("stored stop-loss is not below the entry range");
  if (reasons.length) {
    return closeLine + `<p>No qualifying short-term setup in the stored research (${esc(reasons.join("; "))}). No entry, stop or target arithmetic is shown.</p>`;
  }
  const entryRef = ez.high;
  const riskPerShare = entryRef - stop;
  const required = entryRef + 5 * riskPerShare;
  let position = "";
  if (Number.isFinite(close)) {
    if (close > ez.high) position = `<p>The stored close ${fmtRupee(close)} is above this entry range, so this is a conditional pullback setup: ` +
      `it only becomes relevant if the price falls back into the range. It is not an actionable entry at the stored close.</p>`;
    else if (close < ez.low) position = `<p>The stored close ${fmtRupee(close)} is below this entry range; the setup would need the price to recover into the range first.</p>`;
    else position = `<p>The stored close ${fmtRupee(close)} is inside the entry range as of that session.</p>`;
  }
  const res = daily && Number(daily.resistance);
  const resistanceNote = Number.isFinite(res) && res < required
    ? ` The required price is also above the identified resistance of ${fmtRupee(res)}; the stored research contains no evidence that this level will be broken.`
    : "";
  return closeLine +
    `<table class="kv"><tbody>` +
    `<tr><td>Conditional entry range</td><td>${fmtEntryZone(ez)}</td></tr>` +
    `<tr><td>Stop-loss</td><td>${fmtRupee(stop)} <span class="feed-meta">(stored invalidation level)</span></td></tr>` +
    `<tr><td>Risk per share (from ${fmtRupee(entryRef)} entry)</td><td>${fmtRupee(riskPerShare)}</td></tr>` +
    `</tbody></table>` + position +
    `<p><strong>No verified 1:5 setup:</strong> the stored research holds no evidence-backed price target for this stock.</p>` +
    `<p class="feed-meta">Hypothetical arithmetic only: for a 1:5 reward-to-risk from this entry and stop, the price would need to reach ` +
    `${fmtRupee(required)} (+${(100 * 5 * riskPerShare / entryRef).toFixed(1)}% from the ${fmtRupee(entryRef)} entry; a hypothetical +${fmtRupee(5 * riskPerShare)} per share, ` +
    `or +${fmtRupee(500 * riskPerShare)} on an illustrative 100 shares, against -${fmtRupee(riskPerShare)} per share / -${(100 * riskPerShare / entryRef).toFixed(1)}% if stopped out). ` +
    `This required price is a calculation, not a verified target, and not anyone's actual holding or a realised gain.${resistanceNote} ` +
    `Prices can gap past a stop, and profit is never guaranteed. Research only, no trades.</p>`;
}

function technicalHtml(ta) {
  const d = (ta || {}).daily || {};
  const ltr = (ta || {}).long_term_report || {};
  const emas = d.emas || {};
  const emaLine = ["ema_20", "ema_50", "ema_200"].map(k => Number(emas[k])).every(Number.isFinite)
    ? `20: ${fmtNum(emas.ema_20)} / 50: ${fmtNum(emas.ema_50)} / 200: ${fmtNum(emas.ema_200)}` : null;
  const rows = [
    ["Assessment", (ta || {}).assessment],
    ["Daily trend", [d.trend, d.trend_strength].filter(Boolean).join(", ") || null],
    ["Last close", Number.isFinite(Number(d.last_close)) ? fmtRupee(d.last_close) : null],
    ["RSI (14)", Number.isFinite(Number(d.rsi_14)) ? Number(d.rsi_14).toFixed(1) : null],
    ["MACD histogram", d.macd && Number.isFinite(Number(d.macd.histogram)) ? Number(d.macd.histogram).toFixed(2) : null],
    ["EMA", emaLine],
    ["Support", Number.isFinite(Number(d.support)) ? fmtRupee(d.support) : null],
    ["Resistance", Number.isFinite(Number(d.resistance)) ? fmtRupee(d.resistance) : null],
    ["Relative volume (vs 20-day avg)", Number.isFinite(Number(d.relative_volume)) ? `${Number(d.relative_volume).toFixed(2)}x` : null],
    ["Weekly/monthly trend", ltr.trend || null],
    ["Price vs 200-day EMA", ltr.price_vs_ema_200 || null],
  ].filter(([, v]) => v != null && v !== "");
  if (!rows.length) return "<p>No technical analysis stored for this stock.</p>";
  return `<table class="kv"><tbody>${rows.map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</tbody></table>`;
}

async function openReport(row) {
  const view = document.getElementById("report-view");
  view.classList.remove("hidden");
  view.innerHTML = "<p>Loading report&hellip;</p>";
  try {
    const r = await fetchJson(`${RAW}/${row.file}`);
    const profile = r["1_company_profile"] || {};
    const stamp = r["2_source_and_timestamp"] || {};
    const fin = r["3_financial_analysis"] || {};
    const val = r["6_valuation"] || {};
    const risk = r["8_risk_analysis"] || {};
    const quality = r["5_business_quality"] || {};
    const ta = r["4_technical_analysis"] || {};
    const short = r["12_short_term_assessment"] || {};
    const long_ = r["13_long_term_assessment"] || {};
    const combined = r.combined_scores || {};
    const missing = r["16_missing_evidence"] || {};

    const scoreCards = [
      ["Fundamental", r["9_fundamental_score"]],
      ["Technical", r["10_technical_score"]],
      ["Data confidence", r["11_data_confidence"]],
      ["Long term", combined.long_term],
      ["Short term", combined.short_term],
      ["Balanced", combined.balanced],
      ["Risk (higher=worse)", combined.risk_score_higher_is_worse,
        (risk.unassessed_governance_items || []).length
          ? `${risk.unassessed_governance_items.length} governance items not assessed - score covers quantitative checks only`
          : ""],
    ].map(([label, v, note]) =>
      `<div class="score-card"><span class="label">${label}</span><span class="value">${fmtScore(v)}</span>` +
      `${note ? `<span class="card-note">${esc(note)}</span>` : ""}</div>`
    ).join("");

    const invalidation = (r["15_thesis_invalidation"] || [])
      .map(i => `<li>${esc(i)}</li>`).join("");
    const missingHtml = Object.entries(missing)
      .filter(([, v]) => v && v.length)
      .map(([k, v]) => `<li><em>${esc(k.replace(/_/g, " "))}</em>: ${esc((Array.isArray(v) ? v : [v]).join("; "))}</li>`)
      .join("");
    const sources = (r["17_sources"] || []).map(s => `<li>${esc(s)}</li>`).join("");
    const downloads = Object.entries(row.exports || {})
      .map(([fmt, path]) => `<a href="${RAW}/${esc(path)}" target="_blank" rel="noopener">${fmt.toUpperCase()}</a>`)
      .join("");

    const tv = short.technical_view || {};
    const lt = long_.trend || {};

    view.innerHTML =
      `<h3>${esc(profile.name || row.symbol)} (${esc(profile.symbol || row.symbol)}, ${esc(profile.exchange || "NSE")})</h3>` +
      `<p class="feed-meta">${esc([profile.sector, profile.industry].filter(Boolean).join(" | "))} &middot; ` +
      `Market cap ${fmtNum(profile.market_cap)} &middot; Report generated ${esc(stamp.generated_at || "unknown")} &middot; ` +
      `price data as of ${esc((r.automation || {}).rotation_data_date || "unknown")}</p>` +
      `<div class="report-scores">${scoreCards}</div>` +
      (downloads ? `<p class="downloads">Download: ${downloads}</p>` : "") +
      (r["14_investment_thesis"] ? `<h4>Investment thesis</h4><p>${esc(r["14_investment_thesis"])}</p>` : "") +
      conclusionHtml(r, risk, quality, ta) +
      `<h4>Short-term view <span class="feed-meta">(daily-chart technicals; holding duration not specified in the research)</span></h4>` +
      `<p>Score ${fmtScore(short.score)}; trend ${esc(tv.trend || "n/a")}, RSI(14) ${fmtNum(tv.rsi_14)}.</p>` +
      shortSetupHtml(short, ta.daily, (r.automation || {}).rotation_data_date) +
      `<h4>Long-term view <span class="feed-meta">(weekly/monthly trend and business classification; holding duration not specified in the research)</span></h4>` +
      `<p>Score ${fmtScore(long_.score)}; trend ${esc(lt.trend || "n/a")} (${esc((lt.timeframes || []).join(" + ") || "n/a")}), ` +
      `price vs 200-day EMA: ${esc(lt.price_vs_ema_200 || "n/a")}.<br>Business classification: ${esc(long_.business_classification || "n/a")}.</p>` +
      `<p class="feed-meta">No entry range, stop-loss or target is stored for the long-term horizon, so no 1:5 arithmetic is shown here. ` +
      `Long-term profit depends on business performance over years; it is uncertain and never guaranteed.</p>` +
      (invalidation ? `<h4>What would break this thesis</h4><ul>${invalidation}</ul>` : "") +
      `<h4>Technical analysis</h4>` + technicalHtml(ta) +
      `<h4>Financial analysis</h4>` +
      `<div class="two-col"><div>${kvTable(fin.growth, fmtPct)}</div><div>${kvTable(fin.profitability, fmtPct)}</div></div>` +
      `<div class="two-col"><div>${kvTable(fin.balance_sheet, fmtNum)}</div><div>${kvTable(fin.cash_flow, fmtNum)}</div></div>` +
      ((fin.red_flags || []).length ? `<p><strong>Red flags:</strong> ${esc(fin.red_flags.join("; "))}</p>` : "") +
      `<h4>Valuation</h4>${kvTable(val.multiples, fmtNum)}` +
      (val.dcf_not_calculated_reason ? `<p class="feed-meta">DCF not calculated: ${esc(val.dcf_not_calculated_reason)}</p>` : "") +
      `<h4>Business quality</h4><p>Classification: ${esc(quality.classification || "n/a")}. ${esc(quality.moat_assessment || "")}</p>` +
      `<h4>Risk analysis</h4><p>Classification: ${esc(risk.classification || "n/a")}.</p>` +
      ((risk.unassessed_governance_items || []).length ?
        `<p class="feed-meta">Governance items not assessed (no public source in the free feeds): ${esc(risk.unassessed_governance_items.join("; "))}</p>` : "") +
      (missingHtml ? `<h4>Missing evidence</h4><ul>${missingHtml}</ul>` : "") +
      (sources ? `<h4>Sources</h4><ul>${sources}</ul>` : "") +
      (r.disclaimer ? `<p class="disclaimer">${esc(r.disclaimer)}</p>` : "");
    view.scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    view.innerHTML = `<p class="error-box">Could not load this report: ${esc(err.message)}</p>`;
  }
}


function renderCommand(state) {
  const last = state.last_run || {};
  const stats = [
    ["Last run", state.last_run_at || "unknown"],
    ["Stocks attempted", last.attempted != null ? String(last.attempted) : "n/a"],
    ["Complete", last.complete != null ? String(last.complete) : "n/a"],
    ["Partial data", last.partial != null ? String(last.partial) : "n/a"],
    ["Unavailable", last.unavailable != null ? String(last.unavailable) : "n/a"],
    ["Run length", last.minutes != null ? `${last.minutes} min` : "n/a"],
    ["Universe size", state.universe_size != null ? String(state.universe_size) : "n/a"],
    ["Runs this cycle", state.run_count != null ? String(state.run_count) : "n/a"],
  ];
  document.getElementById("floor00-stats").innerHTML = stats.map(([l, v]) =>
    `<div class="stat-card"><div class="sv">${esc(v)}</div><div class="sl">${esc(l)}</div></div>`).join("");
  setMeta("floor00-meta",
    `One scheduled research run per weekday evening (IST). Cycle started ${state.cycle_started_at || "unknown"}; ` +
    `rotation cursor at ${state.cursor != null ? state.cursor : "n/a"} of ${state.universe_size || "n/a"} stocks.` +
    (state.last_run_stopped_reason ? ` Last run stopped early: ${state.last_run_stopped_reason}` : ""));
}

function renderFloorRisk(feed) {
  const rows = (feed.top || []).slice().sort((a, b) => (b.risk || 0) - (a.risk || 0)).slice(0, 25);
  document.querySelector("#risk-table thead").innerHTML =
    "<tr><th>Symbol</th><th>Company</th><th>Stored risk (higher=worse)</th><th>Verdict</th><th>Data date</th></tr>";
  const body = document.querySelector("#risk-table tbody");
  body.innerHTML = "";
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td><strong>${esc(r.symbol)}</strong></td>` +
      `<td>${esc(r.name || "")}</td>` +
      `<td>${fmtScore(r.risk)}</td>` +
      `<td>${esc(r.verdict || "")}</td>` +
      `<td>${esc(r.data_date || "n/a")}</td>`;
    body.appendChild(tr);
  }
  setMeta("floor03-meta",
    "Highest stored risk scores among ranked candidates. The risk score covers quantitative checks only; " +
    "governance items (auditor history, pledging, related parties, regulatory actions) are not assessed by the free feeds and are named inside each report.");
}

let universeRows = null;
async function loadUniverse() {
  if (universeRows) return universeRows;
  universeRows = [];
  for (const url of UNIVERSE_CSVS) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`universe fetch failed: ${res.status}`);
    const text = await res.text();
    for (const line of text.split("\n").slice(1)) {
      const cols = line.split(",");
      if (cols.length >= 2 && cols[0]) {
        universeRows.push({ symbol: cols[0].trim(), name: (cols[1] || "").trim(), exchange: "NSE" });
      }
    }
  }
  try {
    const res = await fetch(BSE_UNIVERSE_CSV);
    if (res.ok) {
      const text = await res.text();
      for (const line of text.split("\n").slice(1)) {
        const cols = line.split(",");
        if (cols.length >= 2 && cols[0]) {
          universeRows.push({ symbol: cols[0].trim(), name: (cols[1] || "").trim(), exchange: "BSE" });
        }
      }
    }
  } catch (e) { /* BSE universe lands with a future evening run */ }
  return universeRows;
}

function wireUniverseSearch() {
  const input = document.getElementById("universe-search");
  const head = document.querySelector("#universe-table thead");
  const body = document.querySelector("#universe-table tbody");
  head.innerHTML = "<tr><th>Symbol</th><th>Company</th><th>Exchange</th></tr>";
  let loaded = false;
  async function ensure() {
    if (loaded) return;
    loaded = true;
    setMeta("floor01-meta", "Loading universe files...");
    try {
      const rows = await loadUniverse();
      const nse = rows.filter(r => r.exchange === "NSE").length;
      const bse = rows.filter(r => r.exchange === "BSE").length;
      setMeta("floor01-meta",
        `Research universe: ${nse} NSE equities` +
        (bse ? ` + ${bse} BSE instruments from the latest session` :
               "; the BSE session universe is added by the evening automation run") +
        ". Type to filter; first 50 matches shown.");
    } catch (e) {
      setMeta("floor01-meta", `Universe files could not be loaded: ${e.message}`);
    }
  }
  input.addEventListener("focus", ensure);
  input.addEventListener("input", async () => {
    await ensure();
    const needle = input.value.trim().toUpperCase();
    body.innerHTML = "";
    if (!needle || !universeRows) return;
    const matches = universeRows.filter(r =>
      r.symbol.toUpperCase().includes(needle) || r.name.toUpperCase().includes(needle)).slice(0, 50);
    for (const r of matches) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td><strong>${esc(r.symbol)}</strong></td><td>${esc(r.name)}</td>` +
        `<td><span class="badge exchange">${esc(r.exchange)}</span></td>`;
      body.appendChild(tr);
    }
  });
}


function capRow(r) {
  return `<td><strong>${esc(r.symbol)}</strong></td>` +
    `<td>${esc(r.name || "")}</td>` +
    `<td>${fmtScore(r.balanced)}</td>` +
    `<td>${fmtScore(r.risk)}</td>` +
    `<td>${fmtScore(r.data_confidence)}</td>` +
    `<td>${r.close != null ? "\u20B9" + Number(r.close).toFixed(2) : "n/a"}</td>` +
    `<td>${esc(r.data_date || "n/a")}</td>`;
}

function capHead(priceDate) {
  return `<tr><th>Symbol</th><th>Company</th><th>Balanced</th><th>Risk (higher=worse)</th><th>Confidence</th>` +
    `<th>Close (${esc(priceDate)})</th><th>Analysis date</th></tr>`;
}

function priceSessionLabel(data) {
  const m = /session (\d{4}-\d{2}-\d{2})/.exec((data.sources || {}).prices || "");
  return m ? m[1] : "latest session";
}

function renderCapSections(data) {
  const c = data.counts || {};
  const priceDate = priceSessionLabel(data);
  const meta = document.getElementById("caps-meta");
  meta.textContent =
    `Cap classes from the AMFI average market-capitalization list, six months ended 30 June 2026 (per SEBI circular dated Oct 6, 2017). ` +
    `Prices: BSE official equity bhavcopy close, session ${priceDate}. Penny = close below \u20B9${data.penny_cutoff_inr} per share. ` +
    `Unclassified stocks were not in the AMFI list; unpriced stocks were absent from the session file. ` +
    `Sections cover the ${data.ranked_count} stocks researched so far this cycle. ` +
    `Risk scores cover quantitative checks only; governance items are not assessed by the free feeds and are named inside each report. `;
  const links = document.createElement("span");
  links.innerHTML = `Sources: <a href="https://portal.amfiindia.com/spages/AverageMarketCapitalization30Jun2026.pdf" target="_blank" rel="noopener">AMFI list (PDF)</a> · ` +
    `<a href="https://www.bseindia.com/download/Bhavcopy/Equity/BhavCopy_BSE_CM_0_0_0_20261119_F_0000.CSV" target="_blank" rel="noopener">BSE bhavcopy (CSV)</a>`;
  meta.appendChild(links);
  const defs = [
    ["Large cap", data.sections.large_cap, c.large_cap],
    ["Mid cap", data.sections.mid_cap, c.mid_cap],
    ["Small cap", data.sections.small_cap, c.small_cap],
    [`Penny stocks (close < \u20B9${esc(String(data.penny_cutoff_inr))})`, data.penny, c.penny],
  ];
  const host = document.getElementById("cap-sections");
  host.innerHTML = "";
  for (const [title, rows, total] of defs) {
    const div = document.createElement("div");
    div.className = "cap-block";
    const shown = (rows || []).slice(0, 25);
    div.innerHTML = `<h3>${esc(title)} <span class="cap-count">${total || 0} stocks</span></h3>` +
      (total > shown.length ? `<p class="feed-meta">Showing first ${shown.length} of ${total}, ordered by balanced research score.</p>` : "") +
      `<div class="table-wrap"><table><thead>${capHead(priceDate)}</thead><tbody>` +
      shown.map(r => `<tr>${capRow(r)}</tr>`).join("") + "</tbody></table></div>";
    host.appendChild(div);
  }
}

function renderTop50(data) {
  const head = document.querySelector("#ranking-table thead");
  const body = document.querySelector("#ranking-table tbody");
  head.innerHTML = capHead(priceSessionLabel(data));
  body.innerHTML = "";
  for (const r of data.top50 || []) {
    const tr = document.createElement("tr");
    tr.innerHTML = capRow(r);
    body.appendChild(tr);
  }
  setMeta("ranking-meta",
    `Top ${(data.top50 || []).length} candidates by balanced research score out of ${data.ranked_count} stocks researched this cycle. ` +
    `Research ranking, not buy recommendations; scores are ${esc(data.sources.scores)}. Each stock keeps its own data date.`);
}

async function boot() {
  const status = document.getElementById("header-status");
  let failures = 0;
  try {
    const manifest = await fetchJson(FEEDS.manifest);
    renderManifest(manifest);
    status.textContent = `Latest batch generated ${manifest.generated_at || "unknown"}; each stock keeps its own data date`;
    status.classList.add("ok");
  } catch (err) {
    failures++;
    setMeta("reports-meta", "No scheduled run has committed reports yet.");
  }
  try {
    const feed = await fetchJson(FEEDS.ranking);
    renderFloorRisk(feed);
  }
  catch (err) { failures++; setMeta("floor03-meta", "Risk feed not committed yet."); }
  try {
    const caps = await fetchJson(FEEDS.capSections);
    renderTop50(caps);
    renderCapSections(caps);
  }
  catch (err) { failures++; setMeta("ranking-meta", "Cap sections feed not committed yet."); setMeta("caps-meta", "Cap sections feed not committed yet."); }
  try { renderCommand(await fetchJson(FEEDS.rotation)); }
  catch (err) { setMeta("floor00-meta", "Automation health feed not committed yet."); }
  wireUniverseSearch();
  try { renderAlerts(await fetchJson(FEEDS.alerts)); }
  catch (err) { failures++; setMeta("alerts-meta", "Alert feed not committed yet."); }
  if (failures) {
    status.textContent = "Some research feeds are unavailable right now; shown sections are from the latest committed run.";
    status.classList.add("stale");
  }
  document.getElementById("footer-status").textContent =
    "Scheduled batch research - one run per weekday evening IST";
}

boot();
