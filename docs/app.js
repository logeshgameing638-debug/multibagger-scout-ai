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
};

function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmtScore(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `${Math.round(n)}/100` : "n/a";
}

function fmtPct(v) {
  const n = Number(v);
  return Number.isFinite(n) ? `${(n * 100).toFixed(1)}%` : "n/a";
}

function fmtNum(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "n/a";
  if (Math.abs(n) >= 1e7) return `${(n / 1e7).toFixed(1)} Cr`;
  return n.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

function fmtRupee(v) {
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
    `(market-derived research only; not continuous monitoring).`);
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
      `<td><span class="badge ${esc(r.status)}">${esc(r.status)}</span></td>` +
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
      ["Risk (higher=worse)", combined.risk_score_higher_is_worse],
    ].map(([label, v]) =>
      `<div class="score-card"><span class="label">${label}</span><span class="value">${fmtScore(v)}</span></div>`
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
      `<div class="two-col"><div><h4>Short term</h4><p>Score ${fmtScore(short.score)}; trend ${esc(tv.trend || "n/a")}, ` +
      `RSI(14) ${fmtNum(tv.rsi_14)}.${short.entry_zone ? `<br>Entry zone: ${fmtEntryZone(short.entry_zone)}` : ""}` +
      `${short.invalidation_level ? `<br>Invalidation level: ${esc(short.invalidation_level)}` : ""}</p></div>` +
      `<div><h4>Long term</h4><p>Score ${fmtScore(long_.score)}; trend ${esc(lt.trend || "n/a")}, ` +
      `price vs 200-day EMA: ${esc(lt.price_vs_ema_200 || "n/a")}.<br>Business classification: ${esc(long_.business_classification || "n/a")}</p></div></div>` +
      (invalidation ? `<h4>What would break this thesis</h4><ul>${invalidation}</ul>` : "") +
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

async function boot() {
  const status = document.getElementById("header-status");
  let failures = 0;
  try {
    const manifest = await fetchJson(FEEDS.manifest);
    renderManifest(manifest);
    status.textContent = `Research current as of ${manifest.generated_at || "latest run"}`;
    status.classList.add("ok");
  } catch (err) {
    failures++;
    setMeta("reports-meta", "No scheduled run has committed reports yet.");
  }
  try { renderRanking(await fetchJson(FEEDS.ranking)); }
  catch (err) { failures++; setMeta("ranking-meta", "Ranking feed not committed yet."); }
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
