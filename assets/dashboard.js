"use strict";

const nf = new Intl.NumberFormat("en-US");
const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1, minimumFractionDigits: 1 });
const pct0 = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric" });

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);

const formatNumber = (value) => value == null ? "—" : nf.format(Math.round(value));
const formatPct = (value) => value == null ? "—" : pct.format(value);
const formatPct0 = (value) => value == null ? "—" : pct0.format(value);
const formatSigned = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${nf.format(Math.round(value))}`;
const formatSignedPct = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${pct.format(value)}`;
const tone = (value, good = 0, warn = -0.05) => value >= good ? "good" : value >= warn ? "warning" : "danger";
const classForValue = (value) => value > 0 ? "positive" : value < 0 ? "negative" : "muted";
const getQueryCouncil = () => new URLSearchParams(window.location.search).get("council");
const setQueryCouncil = (number) => {
  const url = new URL(window.location.href);
  url.searchParams.set("council", number);
  window.history.replaceState({}, "", url);
};

function councilByNumber(data, number) {
  return data.councils.find((council) => council.council_number === String(number)) || data.selected;
}

function councilOptions(data, selectedNumber) {
  return [...data.councils]
    .sort((a, b) => a.council.localeCompare(b.council))
    .map((council) => `<option value="${escapeHtml(council.council_number)}"${council.council_number === selectedNumber ? " selected" : ""}>${escapeHtml(council.council)}</option>`)
    .join("");
}

function kpiCard(label, value, sub, toneClass = "") {
  return `<article class="kpi ${toneClass}"><span class="kpi-label">${escapeHtml(label)}</span><strong class="kpi-value">${escapeHtml(value)}</strong><span class="kpi-sub">${escapeHtml(sub)}</span></article>`;
}

function metricLine(label, value, valueClass = "") {
  return `<div class="metric-line"><span>${escapeHtml(label)}</span><strong class="${valueClass}">${escapeHtml(value)}</strong></div>`;
}

function peerSet(data, selected) {
  return data.councils
    .filter((record) => record.council !== selected.council
      && record.units / selected.units >= 0.8 && record.units / selected.units <= 1.2
      && record.current_youth / selected.current_youth >= 0.8 && record.current_youth / selected.current_youth <= 1.2)
    .sort((a, b) => b.yoy_pct - a.yoy_pct || a.council.localeCompare(b.council));
}

function chartRow(label, detail, value, maxAbs, valueFormatter = formatSignedPct) {
  const width = Math.max(2, Math.abs(value || 0) / Math.max(maxAbs, .001) * 100);
  return `<div class="chart-row">
    <div class="chart-label">${escapeHtml(label)}<span>${escapeHtml(detail)}</span></div>
    <div class="bar ${value < 0 ? "negative" : ""}" aria-hidden="true"><span style="width:${Math.min(100, width).toFixed(1)}%"></span></div>
    <strong class="bar-value ${classForValue(value)}">${escapeHtml(valueFormatter(value))}</strong>
  </div>`;
}

function updateSourceDates(data) {
  const sourceDate = dateFmt.format(new Date(data.metadata.source_downloaded_at));
  document.querySelectorAll("[data-source-date]").forEach((element) => { element.textContent = sourceDate; });
}

function renderOverview(data, selected) {
  const peers = peerSet(data, selected);
  const percentile = Math.round((1 - (selected.yoy_rank - 1) / Math.max(1, data.national.council_count - 1)) * 100);
  document.getElementById("focusNote").textContent = `${selected.council} · ${peers.length} comparable councils`;
  document.getElementById("overviewKpis").innerHTML = [
    kpiCard("Current youth", formatNumber(selected.current_youth), `${formatSigned(selected.yoy_delta)} year over year`, tone(selected.yoy_pct)),
    kpiCard("YOY growth", formatSignedPct(selected.yoy_pct), `National: ${formatSignedPct(data.national.yoy_pct)}`, tone(selected.yoy_pct)),
    kpiCard("National rank", `#${selected.yoy_rank}`, `Top ${100 - percentile}% by growth`, "teal"),
    kpiCard("Registered units", formatNumber(selected.units), `${(selected.current_youth / selected.units).toFixed(1)} youth per unit`),
    kpiCard("YE ’25 change", formatSignedPct(selected.year_end_pct), `${formatSigned(selected.year_end_delta)} youth`, tone(selected.year_end_pct)),
    kpiCard("Peer set", formatNumber(peers.length), "±20% units and current youth", "teal"),
  ].join("");

  document.getElementById("peerTitle").textContent = `Comparable to ${selected.council.replace(/\s\d{3}$/, "")}`;
  document.getElementById("peerCount").textContent = `${peers.length} peers`;
  const peerRows = [...peers, selected].sort((a, b) => b.yoy_pct - a.yoy_pct || a.council.localeCompare(b.council));
  const maxAbs = Math.max(...peerRows.map((record) => Math.abs(record.yoy_pct || 0)), .01);
  document.getElementById("peerChart").innerHTML = peerRows.length
    ? peerRows.map((record) => chartRow(
      record.council.replace(/\s\d{3}$/, ""),
      record.council === selected.council ? "Focus council" : `${formatNumber(record.current_youth)} youth · ${formatNumber(record.units)} units`,
      record.yoy_pct,
      maxAbs,
    )).join("")
    : '<div class="empty-state">No scale-matched peers were found.</div>';

  const peerAverage = peers.length ? peers.reduce((sum, record) => sum + record.yoy_pct, 0) / peers.length : null;
  const unitHealth = data.unit_metrics["All Units"].find((record) => record.council === selected.council);
  const signals = [
    {
      title: selected.yoy_pct >= data.national.yoy_pct ? "Growth is ahead of the national total" : "Growth trails the national total",
      body: `${selected.council} is ${formatSignedPct(selected.yoy_pct - data.national.yoy_pct)} versus the aggregate national rate.`,
    },
    {
      title: peerAverage == null ? "Peer comparison unavailable" : selected.yoy_pct >= peerAverage ? "Outperforming scale peers" : "Peer growth is stronger",
      body: peerAverage == null ? "No councils met both scale bands." : `The ${peers.length}-council peer average is ${formatSignedPct(peerAverage)}.`,
    },
    {
      title: unitHealth ? `${formatPct0(unitHealth.metric_low_rate)} of units score 0–2` : "Unit health data unavailable",
      body: unitHealth ? `Average unit metric is ${unitHealth.average_metric?.toFixed(2) ?? "—"}; ${formatPct0(unitHealth.trained_rate)} meet the workbook’s training signal.` : "The selected council has no matching unit metric record.",
    },
  ];
  document.getElementById("signals").innerHTML = signals.map((signal) => `<article class="signal"><strong>${escapeHtml(signal.title)}</strong><p>${escapeHtml(signal.body)}</p></article>`).join("");

  document.getElementById("growthRows").innerHTML = data.top_growth.map((record) => `<tr${record.council === selected.council ? ' class="focus-row"' : ""}><td>#${record.yoy_rank}</td><td><strong>${escapeHtml(record.council)}</strong></td><td class="num">${formatNumber(record.current_youth)}</td><td class="num ${classForValue(record.yoy_delta)}">${formatSigned(record.yoy_delta)}</td><td class="num ${classForValue(record.yoy_pct)}">${formatSignedPct(record.yoy_pct)}</td></tr>`).join("");

  document.getElementById("nationalContext").innerHTML = [
    metricLine("Councils ranked", formatNumber(data.national.council_count)),
    metricLine("Current youth", formatNumber(data.national.current_youth)),
    metricLine("Registered units", formatNumber(data.national.units)),
    metricLine("YOY movement", formatSigned(data.national.yoy_delta), classForValue(data.national.yoy_delta)),
    metricLine("Aggregate growth", formatSignedPct(data.national.yoy_pct), classForValue(data.national.yoy_pct)),
    metricLine("Councils growing", `${formatNumber(data.national.positive_growth_councils)} of ${formatNumber(data.national.council_count)}`),
  ].join("");

  document.getElementById("sourceSummary").textContent = `${data.metadata.source_name}, downloaded ${dateFmt.format(new Date(data.metadata.source_downloaded_at))}. Growth rates and ranks are recalculated from the workbook’s cached current, prior-year, and 2025 year-end council totals.`;
}

function initOverview(data) {
  const select = document.getElementById("councilSelect");
  let selected = councilByNumber(data, getQueryCouncil() || data.selected.council_number);
  select.innerHTML = councilOptions(data, selected.council_number);
  select.addEventListener("change", () => {
    selected = councilByNumber(data, select.value);
    setQueryCouncil(selected.council_number);
    renderOverview(data, selected);
  });
  renderOverview(data, selected);
}

function renderRankings(data) {
  const search = document.getElementById("rankingSearch").value.trim().toLowerCase();
  const scope = document.getElementById("rankingScope").value;
  const focus = councilByNumber(data, document.getElementById("rankingCouncil").value);
  const sort = document.getElementById("rankingSort").value;
  let rows = scope === "peers" ? [...peerSet(data, focus), focus] : [...data.councils];
  if (search) rows = rows.filter((record) => record.council.toLowerCase().includes(search) || record.council_number.includes(search));
  const sorters = {
    yoy_rank: (a, b) => a.yoy_rank - b.yoy_rank || a.council.localeCompare(b.council),
    yoy_pct_desc: (a, b) => b.yoy_pct - a.yoy_pct || a.council.localeCompare(b.council),
    current_youth_desc: (a, b) => b.current_youth - a.current_youth || a.council.localeCompare(b.council),
    year_end_rank: (a, b) => a.year_end_rank - b.year_end_rank || a.council.localeCompare(b.council),
    name: (a, b) => a.council.localeCompare(b.council),
  };
  rows.sort(sorters[sort]);
  document.getElementById("rankingCount").textContent = `${formatNumber(rows.length)} councils`;
  document.getElementById("rankingRows").innerHTML = rows.length ? rows.map((record) => `<tr${record.council === focus.council ? ' class="focus-row"' : ""}>
    <td>#${record.yoy_rank}</td><td><strong>${escapeHtml(record.council)}</strong></td><td class="num">${formatNumber(record.units)}</td><td class="num">${formatNumber(record.current_youth)}</td><td class="num">${formatNumber(record.prior_youth)}</td><td class="num ${classForValue(record.yoy_delta)}">${formatSigned(record.yoy_delta)}</td><td class="num ${classForValue(record.yoy_pct)}">${formatSignedPct(record.yoy_pct)}</td><td class="num ${classForValue(record.year_end_pct)}">${formatSignedPct(record.year_end_pct)}</td><td><a class="detail-link" href="index.html?council=${record.council_number}">Overview</a></td>
  </tr>`).join("") : '<tr><td colspan="9" class="empty-state">No councils match these filters.</td></tr>';
  document.getElementById("rankingKpis").innerHTML = [
    kpiCard("Focus rank", `#${focus.yoy_rank}`, focus.council, "teal"),
    kpiCard("Focus growth", formatSignedPct(focus.yoy_pct), `${formatSigned(focus.yoy_delta)} youth`, tone(focus.yoy_pct)),
    kpiCard("Visible councils", formatNumber(rows.length), scope === "peers" ? "Focus plus scale peers" : "Current search result"),
    kpiCard("National growth", formatSignedPct(data.national.yoy_pct), `${formatSigned(data.national.yoy_delta)} youth`, tone(data.national.yoy_pct)),
  ].join("");
}

function initRankings(data) {
  const focus = councilByNumber(data, getQueryCouncil() || data.selected.council_number);
  const councilSelect = document.getElementById("rankingCouncil");
  councilSelect.innerHTML = councilOptions(data, focus.council_number);
  ["rankingSearch", "rankingScope", "rankingCouncil", "rankingSort"].forEach((id) => {
    const element = document.getElementById(id);
    element.addEventListener(id === "rankingSearch" ? "input" : "change", () => {
      if (id === "rankingCouncil") setQueryCouncil(element.value);
      renderRankings(data);
    });
  });
  renderRankings(data);
}

function comparisonRow(label, selectedValue, nationalValue, formatter = formatPct0) {
  return `<div class="comparison-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(formatter(selectedValue))}</strong><strong>${escapeHtml(formatter(nationalValue))}</strong></div>`;
}

function renderHealth(data) {
  const council = councilByNumber(data, document.getElementById("healthCouncil").value);
  const program = document.getElementById("programSelect").value;
  const metric = data.unit_metrics[program].find((record) => record.council === council.council);
  const national = data.program_summaries[program];
  document.getElementById("healthProgramLabel").textContent = program;
  if (!metric) {
    document.getElementById("healthKpis").innerHTML = kpiCard("No data", "—", `${council.council} has no ${program.toLowerCase()} metric row.`, "warning");
    document.getElementById("metricMix").innerHTML = '<div class="empty-state">No unit metric record is available for this council and program.</div>';
    document.getElementById("healthComparison").innerHTML = "";
    document.getElementById("capabilityChart").innerHTML = "";
  } else {
    document.getElementById("healthKpis").innerHTML = [
      kpiCard("Average metric", metric.average_metric?.toFixed(2) ?? "—", `National ${national.average_metric?.toFixed(2) ?? "—"}`, metric.average_metric >= national.average_metric ? "good" : "warning"),
      kpiCard("Units", formatNumber(metric.units), `${program} in ${council.council_number}`),
      kpiCard("Metric 0–2", formatPct0(metric.metric_low_rate), `${formatNumber(metric.metric_low_count)} units`, metric.metric_low_rate <= national.metric_low_count / national.units ? "good" : "danger"),
      kpiCard("UL & CC trained", formatPct0(metric.trained_rate), `National ${formatPct0(national.trained_rate)}`, metric.trained_rate >= national.trained_rate ? "good" : "warning"),
      kpiCard("Youth growth", formatSignedPct(metric.youth_growth_rate), `${formatSigned(metric.youth_delta)} youth`, tone(metric.youth_growth_rate)),
      kpiCard("Youth", formatNumber(metric.youth_current), `${formatNumber(metric.youth_prior)} prior year`),
    ].join("");

    const total = (metric.metric_low_count || 0) + (metric.metric_mid_count || 0) + (metric.metric_high_count || 0);
    const width = (value) => total ? value / total * 100 : 0;
    document.getElementById("metricMix").innerHTML = `<div class="mix-total">
      <div class="mix-segment low"><strong>${formatNumber(metric.metric_low_count)}</strong><span>Metric 0–2 · ${formatPct0(metric.metric_low_rate)}</span></div>
      <div class="mix-segment mid"><strong>${formatNumber(metric.metric_mid_count)}</strong><span>Metric 3 · ${formatPct0(metric.metric_mid_rate)}</span></div>
      <div class="mix-segment high"><strong>${formatNumber(metric.metric_high_count)}</strong><span>Metric 4–5 · ${formatPct0(metric.metric_high_rate)}</span></div>
    </div><div class="stacked-bar" aria-label="Unit metric distribution"><span class="low" style="width:${width(metric.metric_low_count || 0)}%"></span><span class="mid" style="width:${width(metric.metric_mid_count || 0)}%"></span><span class="high" style="width:${width(metric.metric_high_count || 0)}%"></span></div>`;

    document.getElementById("healthComparison").innerHTML = `<div class="comparison-row comparison-head"><span>Measure</span><strong>Council</strong><strong>National</strong></div>${[
      comparisonRow("Average metric", metric.average_metric, national.average_metric, (value) => value == null ? "—" : value.toFixed(2)),
      comparisonRow("Metric 0–2", metric.metric_low_rate, national.metric_low_count / national.units),
      comparisonRow("UL & CC trained", metric.trained_rate, national.trained_rate),
      comparisonRow("Healthy size", metric.healthy_size_rate, national.healthy_size_rate),
      comparisonRow("Youth growth", metric.youth_growth_rate, national.youth_growth_rate, formatSignedPct),
    ].join("")}`;

    const capabilities = [
      ["UL & CC trained", metric.trained_rate],
      ["Exceeds small-unit threshold", metric.healthy_size_rate],
      ["Units with membership growth", metric.membership_growth_unit_rate],
      ["Advancement / leadership", metric.advancement_rate],
      ["Outdoor activity", metric.outdoor_rate],
      ["Retention", metric.retention_rate],
    ];
    document.getElementById("capabilityChart").innerHTML = capabilities.map(([label, value]) => chartRow(label, `${program} workbook signal`, value, Math.max(1, value || 0), formatPct0)).join("");
  }

  const pin = council.pin;
  document.getElementById("pinProfile").innerHTML = pin ? [
    metricLine("PIN active", formatPct0(pin.pin_active_rate)),
    metricLine("Apply active", formatPct0(pin.apply_active_rate)),
    metricLine("Updated in a year", formatPct0(pin.updated_in_year_rate)),
    metricLine("Meeting day listed", formatPct0(pin.meeting_day_rate)),
    metricLine("Trial visit allowed", formatPct0(pin.trial_visit_rate)),
    metricLine("Unit fee listed", formatPct0(pin.unit_fee_rate)),
  ].join("") : '<div class="empty-state">No Unit PIN record is available.</div>';
}

function initHealth(data) {
  const council = councilByNumber(data, getQueryCouncil() || data.selected.council_number);
  const select = document.getElementById("healthCouncil");
  select.innerHTML = councilOptions(data, council.council_number);
  select.addEventListener("change", () => { setQueryCouncil(select.value); renderHealth(data); });
  document.getElementById("programSelect").addEventListener("change", () => renderHealth(data));
  renderHealth(data);
}

function initAbout(data) {
  document.getElementById("methodSource").textContent = `${data.metadata.source_name} was downloaded ${dateFmt.format(new Date(data.metadata.source_downloaded_at))}. The site data was generated ${dateFmt.format(new Date(data.metadata.generated_at))} from cached workbook values.`;
}

function showError(error) {
  const main = document.querySelector("main");
  const banner = document.createElement("div");
  banner.className = "error-banner";
  banner.textContent = `The dashboard data could not be loaded: ${error.message}`;
  main.prepend(banner);
}

async function main() {
  try {
    const response = await fetch("data/latest.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    updateSourceDates(data);
    const page = document.body.dataset.page;
    if (page === "overview") initOverview(data);
    if (page === "rankings") initRankings(data);
    if (page === "unit-health") initHealth(data);
    if (page === "about") initAbout(data);
  } catch (error) {
    showError(error);
  }
}

main();
