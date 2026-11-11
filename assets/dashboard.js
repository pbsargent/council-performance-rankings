"use strict";

const nf = new Intl.NumberFormat("en-US");
const pct = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1, minimumFractionDigits: 1 });
const pct0 = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 0 });
const pct2 = new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 });
const points = new Intl.NumberFormat("en-US", { signDisplay: "exceptZero", minimumFractionDigits: 1, maximumFractionDigits: 1 });
const dateFmt = new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric" });

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);

const formatNumber = (value) => value == null ? "—" : nf.format(Math.round(value));
const formatPct = (value) => value == null ? "—" : pct.format(value);
const formatPct0 = (value) => value == null ? "—" : pct0.format(value);
const formatPct2 = (value) => value == null ? "—" : pct2.format(value);
const formatSignedPct2 = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${pct2.format(value)}`;
const formatSigned = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${nf.format(Math.round(value))}`;
const formatSignedPct = (value) => value == null ? "—" : `${value > 0 ? "+" : ""}${pct.format(value)}`;
const formatRank = (value) => value == null ? "—" : `#${nf.format(value)}`;
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

function unitBreakdown(record) {
  return record.coming_units == null
    ? "Chartered and Coming split unavailable"
    : `${formatNumber(record.units - record.coming_units)} chartered · ${formatNumber(record.coming_units)} Coming`;
}

function peerSet(data, selected) {
  return data.councils
    .filter((record) => record.council !== selected.council
      && record.units / selected.units >= 0.8 && record.units / selected.units <= 1.2
      && record.current_youth / selected.current_youth >= 0.8 && record.current_youth / selected.current_youth <= 1.2
      && record.tay / selected.tay >= 0.8 && record.tay / selected.tay <= 1.2)
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

function sourceLink(data) {
  const url = escapeHtml(data.metadata.source_url);
  return `<a class="source-link" href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`;
}

const totalCounts = (counts) => counts.reduce((sum, count) => sum + count, 0);
const geographyDate = (snapshot) => dateFmt.format(new Date(snapshot.report_date + "T12:00:00"));
const geographyUnavailable = '<div class="empty-state">Unit locations are unavailable for this council.</div>';

function ruralUnitShare(row) {
  const matched = row?.matched ? totalCounts(row.matched) : 0;
  return matched ? row.matched[1] / matched : null;
}

function geographyBar(label, value, population = false) {
  return `<div class="chart-row geography-row${population ? " residents" : ""}">
    <span class="chart-label">${escapeHtml(label)}</span>
    <div class="bar" aria-hidden="true"><span style="width:${(value * 100).toFixed(2)}%"></span></div>
    <strong class="bar-value">${formatPct(value)}</strong>
  </div>`;
}

function renderOverviewGeography(snapshot, council) {
  const target = document.getElementById("overviewGeography");
  const row = snapshot?.councils[council.council_number];
  if (!row) {
    target.innerHTML = geographyUnavailable;
    return;
  }
  const reported = totalCounts(row.units);
  const matched = row.matched ? totalCounts(row.matched) : 0;
  const eligible = Object.values(snapshot.councils).filter((r) => r.matched && totalCounts(r.matched) * 10 >= totalCounts(r.units) * 9);
  const above = eligible.filter((r) => r.matched[1] / totalCounts(r.matched) > r.residents_rural_zip).length;
  const reference = row.census_urban == null ? "Unavailable" : formatPct(1 - row.census_urban);
  const comparison = matched ? (() => {
    const share = ruralUnitShare(row);
    const gap = (share - row.residents_rural_zip) * 100;
    return `<div class="chart-list">${geographyBar("Units in majority-rural ZIP areas", share)}
      ${geographyBar("Residents in majority-rural ZIP areas", row.residents_rural_zip, true)}</div>
      <p><strong>${points.format(gap)} percentage points</strong> · unit share minus resident share</p>`;
  })() : '<div class="empty-state">A comparison using the same ZIP areas is unavailable.</div>';
  target.innerHTML = `${comparison}
    ${metricLine("Residents in Census-defined rural areas (2020)", reference)}
    <p class="geography-note">${matched ? `${formatNumber(matched)} of ${formatNumber(reported)} reported units classified within matched council ZIP areas (${formatPct(matched / reported)} coverage).` : `${formatNumber(reported)} units in the pin report.`}
      Pin report: ${escapeHtml(geographyDate(snapshot))}. Resident shares use the 2020 Census.</p>
    ${eligible.length ? `<p class="geography-note">National context: ${formatNumber(above)} of ${formatNumber(eligible.length)} councils with at least 90% matched unit coverage had a higher rural share of units than residents under the same ZIP rule.</p>` : ""}`;
}

function renderRuralPeerChart(snapshot, selected, peers) {
  const target = document.getElementById("ruralPeerChart");
  if (!snapshot) {
    target.innerHTML = '<div class="empty-state">Peer geography is unavailable.</div>';
    return;
  }
  const rows = [selected, ...peers].map((council) => {
    const geography = snapshot.councils[council.council_number];
    const units = ruralUnitShare(geography);
    const residents = geography?.residents_rural_zip ?? null;
    const gap = units == null || residents == null ? null : (units - residents) * 100;
    return { council, geography, units, residents, gap };
  }).sort((a, b) => (b.gap ?? -Infinity) - (a.gap ?? -Infinity) || a.council.council.localeCompare(b.council.council));
  const limit = Math.max(5, Math.ceil(Math.max(...rows.map(({ gap }) => Math.abs(gap ?? 0))) / 5) * 5);
  const usablePeers = rows.filter(({ council, gap }) => council !== selected && gap != null).length;
  target.innerHTML = `<p class="panel-intro">Unit share minus resident share in majority-rural ZIP areas, in percentage points. Peer selection uses the same ±20% bands as the growth comparison.</p>
    <p class="geography-note">${peers.length ? `${formatNumber(usablePeers)} of ${formatNumber(peers.length)} peers have comparable ZIP data.` : "No scale-matched peers were found."}</p>
    <div class="chart-list rural-peer-list">
      <div class="rural-peer-row rural-peer-axis" aria-hidden="true"><span></span><div><span>−${limit}</span><span>0</span><span>+${limit}</span></div><span></span></div>
      ${rows.map(({ council, geography, units, residents, gap }) => {
        const focus = council === selected;
        const label = escapeHtml(council.council);
        const tag = focus ? "Focus council · " : "";
        const detail = gap == null ? `${tag}Matched ZIP comparison unavailable`
          : `${tag}${formatPct(units)} units · ${formatPct(residents)} residents · ${formatPct(totalCounts(geography.matched) / totalCounts(geography.units))} coverage`;
        const width = Math.abs(gap ?? 0) / (limit * 2) * 100;
        return `<div class="rural-peer-row${focus ? " rural-peer-focus" : ""}">
          <div class="chart-label">${label}<span>${detail}</span></div>
          <div class="rural-peer-track" aria-hidden="true">${gap == null ? "" : `<span style="left:${gap < 0 ? 50 - width : 50}%;width:${width}%"></span>`}</div>
          <strong class="rural-peer-value">${gap == null ? "—" : points.format(gap)}</strong>
        </div>`;
      }).join("")}
    </div>`;
}

function renderProgramGeography(snapshot, council) {
  const target = document.getElementById("programGeography");
  const row = snapshot?.councils[council.council_number];
  if (!row) {
    target.innerHTML = geographyUnavailable;
    return;
  }
  const programs = [["All programs", row.units], ...Object.entries(row.programs)];
  target.innerHTML = `<div class="table-wrap"><table class="program-table" aria-label="Unit locations by program">
    <thead><tr><th scope="col">Program</th><th class="num" scope="col">Urban</th><th class="num" scope="col">Rural</th><th class="num" scope="col">Classified / reported</th></tr></thead>
    <tbody>${programs.map(([name, [urban, rural, unknown]]) => {
      const classified = urban + rural;
      return `<tr><th scope="row">${escapeHtml(name)}</th><td class="num">${formatPct(classified ? urban / classified : null)}</td>
        <td class="num">${formatPct(classified ? rural / classified : null)}</td><td class="num">${formatNumber(classified)} / ${formatNumber(classified + unknown)}</td></tr>`;
    }).join("")}</tbody></table></div>
    <p class="geography-note">Pin report: ${escapeHtml(geographyDate(snapshot))}. Shares use all classified pins for the selected council. Exploring combines posts and clubs. ZIP areas are classified by their majority population.</p>`;
}

function renderOverview(data, selected) {
  renderOverviewGeography(data.unitGeography, selected);
  const peers = peerSet(data, selected);
  renderRuralPeerChart(data.unitGeography, selected, peers);
  const percentile = Math.round((1 - (selected.yoy_rank - 1) / Math.max(1, data.national.council_count - 1)) * 100);
  document.getElementById("focusNote").textContent = `${selected.council} · ${peers.length} comparable councils`;
  document.getElementById("overviewKpis").innerHTML = [
    kpiCard("Current youth", formatNumber(selected.current_youth), `${formatSigned(selected.yoy_delta)} year over year`, tone(selected.yoy_pct)),
    kpiCard("YOY growth", formatSignedPct(selected.yoy_pct), `National: ${formatSignedPct(data.national.yoy_pct)}`, tone(selected.yoy_pct)),
    kpiCard("National rank", `#${selected.yoy_rank}`, `Top ${100 - percentile}% by growth`, "teal"),
    kpiCard("Total units", formatNumber(selected.units), `${unitBreakdown(selected)}${selected.units > 0 ? ` · ${(selected.current_youth / selected.units).toFixed(1)} youth per reported unit` : ""}`),
    kpiCard("TAY penetration", formatPct(selected.tay_pct), `Rank ${formatRank(selected.tay_rank)} where available`, "teal"),
    kpiCard("Urban population", formatPct(selected.urban_pct), "2020 Census urban population share", "teal"),
    kpiCard("Square miles", formatNumber(selected.square_miles), "Matched ZIP land area"),
    kpiCard("Peer set", formatNumber(peers.length), "±20% units, youth, and TAY", "teal"),
  ].join("");

  document.getElementById("peerTitle").textContent = `${selected.council.replace(/\s\d{3}$/, "")} compared with peers`;
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
      title: selected.tay_pct == null ? "TAY context unavailable" : `TAY penetration ranks ${formatRank(selected.tay_rank)}`,
      body: selected.tay_pct == null ? "The workbook does not supply a TAY value for this council." : `${formatNumber(selected.current_youth)} current youth represent ${formatPct(selected.tay_pct)} of ${formatNumber(selected.tay)} TAY in the workbook's market context.`,
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
    metricLine("TAY population", formatNumber(data.national.tay)),
    metricLine("TAY penetration", `${formatPct(data.national.tay_pct)} · ${formatNumber(data.national.tay_covered_councils)} councils`),
    metricLine("Total units", formatNumber(data.national.units)),
    metricLine("Unit breakdown", unitBreakdown(data.national)),
    metricLine("YOY movement", formatSigned(data.national.yoy_delta), classForValue(data.national.yoy_delta)),
    metricLine("Aggregate growth", formatSignedPct(data.national.yoy_pct), classForValue(data.national.yoy_pct)),
    metricLine("Councils growing", `${formatNumber(data.national.positive_growth_councils)} of ${formatNumber(data.national.council_count)}`),
  ].join("");

  document.getElementById("sourceSummary").innerHTML = `${sourceLink(data)}<span>${escapeHtml(data.metadata.source_name)}, downloaded ${escapeHtml(dateFmt.format(new Date(data.metadata.source_downloaded_at)))}. Growth rates and ranks are recalculated from the workbook’s cached current, prior-year, and 2025 year-end council totals. TAY penetration is current youth divided by the workbook's TAY value where supplied.</span>`;
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
    tay_rank: (a, b) => a.tay_rank - b.tay_rank || a.council.localeCompare(b.council),
    tay_pct_desc: (a, b) => b.tay_pct - a.tay_pct || a.council.localeCompare(b.council),
    urban_pct_desc: (a, b) => (b.urban_pct ?? -Infinity) - (a.urban_pct ?? -Infinity) || a.council.localeCompare(b.council),
    square_miles_desc: (a, b) => (b.square_miles ?? -Infinity) - (a.square_miles ?? -Infinity) || a.council.localeCompare(b.council),
    name: (a, b) => a.council.localeCompare(b.council),
  };
  rows.sort(sorters[sort]);
  document.getElementById("rankingCount").textContent = `${formatNumber(rows.length)} councils`;
  document.getElementById("rankingRows").innerHTML = rows.length ? rows.map((record) => `<tr${record.council === focus.council ? ' class="focus-row"' : ""}>
    <td>#${record.yoy_rank}</td><td><strong>${escapeHtml(record.council)}</strong></td><td class="num">${formatNumber(record.units)}</td><td class="num">${formatNumber(record.current_youth)}</td><td class="num">${formatNumber(record.prior_youth)}</td><td class="num ${classForValue(record.yoy_delta)}">${formatSigned(record.yoy_delta)}</td><td class="num ${classForValue(record.yoy_pct)}">${formatSignedPct(record.yoy_pct)}</td><td class="num ${classForValue(record.year_end_pct)}">${formatSignedPct(record.year_end_pct)}</td><td class="num">${formatPct(record.tay_pct)}</td><td class="num">${formatRank(record.tay_rank)}</td><td class="num">${formatPct(record.urban_pct)}</td><td class="num">${formatNumber(record.square_miles)}</td><td><a class="detail-link" href="index.html?council=${record.council_number}">Overview</a></td>
  </tr>`).join("") : '<tr><td colspan="13" class="empty-state">No councils match these filters.</td></tr>';
  document.getElementById("rankingKpis").innerHTML = [
    kpiCard("Focus rank", `#${focus.yoy_rank}`, focus.council, "teal"),
    kpiCard("Focus growth", formatSignedPct(focus.yoy_pct), `${formatSigned(focus.yoy_delta)} youth`, tone(focus.yoy_pct)),
    kpiCard("Focus TAY penetration", formatPct(focus.tay_pct), `Rank ${formatRank(focus.tay_rank)}`, "teal"),
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
  renderProgramGeography(data.unitGeography, council);
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
      ["Imported “retention”*", metric.retention_rate],
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
  document.getElementById("methodSource").innerHTML = `${sourceLink(data)}<span>${escapeHtml(data.metadata.source_name)} was downloaded ${escapeHtml(dateFmt.format(new Date(data.metadata.source_downloaded_at)))}. The site data was generated ${escapeHtml(dateFmt.format(new Date(data.metadata.generated_at)))} from cached workbook values.</span>`;
}

// CSTs are source assignments, never a fixed list of territories or councils.
function cstGroups(councils) {
  const groups = new Map();
  for (const council of councils) {
    const key = council.cst == null ? "unassigned" : String(council.cst);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(council);
  }
  return [...groups].sort(([a], [b]) => a.localeCompare(b, "en", { numeric: true }));
}

const cstLabel = (key) => key === "unassigned" ? "Unassigned CST" : `CST ${key}`;

function membershipSummary(rows) {
  // Missing observations stay unavailable. TAY uses only the covered councils
  // for BOTH numerator and denominator, just like the national payload.
  const sum = (field) => rows.length && rows.every((row) => row[field] != null)
    ? rows.reduce((total, row) => total + row[field], 0) : null;
  const current = sum("current_youth");
  const prior = sum("prior_youth");
  const yearEnd = sum("year_end_youth");
  const covered = rows.filter((row) => row.tay != null && row.tay > 0);
  const tay = covered.reduce((total, row) => total + row.tay, 0);
  const tayYouth = covered.reduce((total, row) => total + row.current_youth, 0);
  const delta = current == null || prior == null ? null : current - prior;
  const yearEndDelta = current == null || yearEnd == null ? null : current - yearEnd;
  return { councils: rows.length, units: sum("units"), coming_units: sum("coming_units"), current_youth: current,
    prior_youth: prior, yoy_delta: delta, yoy_pct: prior > 0 && delta != null ? delta / prior : null,
    year_end_youth: yearEnd, year_end_delta: yearEndDelta,
    year_end_pct: yearEnd > 0 && yearEndDelta != null ? yearEndDelta / yearEnd : null,
    tay: covered.length ? tay : null, tay_pct: tay > 0 ? tayYouth / tay : null,
    tay_covered_councils: covered.length };
}

function cstCouncilDetail(data, council, printable = false) {
  const changeRate = printable ? formatSignedPct2 : formatSignedPct;
  const membership = [
    metricLine(printable ? "Current primary youth" : "Current youth", formatNumber(council.current_youth)),
    metricLine(printable ? "Prior-year primary youth" : "Prior-year youth", formatNumber(council.prior_youth)),
    metricLine("YOY change", `${formatSigned(council.yoy_delta)} · ${changeRate(council.yoy_pct)}`, classForValue(council.yoy_delta)),
    metricLine("2025 year-end youth", formatNumber(council.year_end_youth)),
    metricLine("Change since year-end", `${formatSigned(council.year_end_delta)} · ${changeRate(council.year_end_pct)}`, classForValue(council.year_end_delta)),
    metricLine("National YOY / year-end rank", `${formatRank(council.yoy_rank)} / ${formatRank(council.year_end_rank)}`),
    metricLine("Total units", formatNumber(council.units)),
    metricLine("Unit breakdown", unitBreakdown(council)),
  ].join("");
  const market = [
    metricLine("TAY population", formatNumber(council.tay)),
    metricLine("TAY penetration", (printable ? formatPct2 : formatPct)(council.tay_pct)),
    metricLine("National TAY rank", formatRank(council.tay_rank)),
    metricLine("Square miles", formatNumber(council.square_miles)),
    metricLine("Urban population (2020)", formatPct(council.urban_pct)),
  ].join("");
  const pin = council.pin;
  const pins = pin ? [
    metricLine("Unit PIN population", formatNumber(pin.units)),
    ...[["PIN active", "pin_active_rate"], ["Apply active", "apply_active_rate"],
      ["Fundraising active", "fundraising_active_rate"], ["Trial visit allowed", "trial_visit_rate"],
      ["Unit fee listed", "unit_fee_rate"], ["Updated in a year", "updated_in_year_rate"],
      ["Meeting day listed", "meeting_day_rate"]].map(([label, key]) => metricLine(label, formatPct0(pin[key]))),
  ].join("") : '<p class="muted">No Unit PIN record is available.</p>';
  const programs = Object.entries(data.unit_metrics).map(([program, rows]) => {
    const metric = rows.find((row) => row.council_number === council.council_number);
    if (!metric) return `<tr><th scope="row">${escapeHtml(program)}</th><td colspan="11">No metric record available</td></tr>`;
    return `<tr><th scope="row">${escapeHtml(program)}</th><td class="num">${formatNumber(metric.units)}</td><td class="num">${formatNumber(metric.youth_current)}</td><td class="num ${classForValue(metric.youth_growth_rate)}">${formatSignedPct(metric.youth_growth_rate)}</td><td class="num">${metric.average_metric?.toFixed(2) ?? "—"}</td><td class="num">${formatPct0(metric.metric_low_rate)}</td><td class="num">${formatPct0(metric.trained_rate)}</td><td class="num">${formatPct0(metric.healthy_size_rate)}</td><td class="num">${formatPct0(metric.membership_growth_unit_rate)}</td><td class="num">${formatPct0(metric.advancement_rate)}</td><td class="num">${formatPct0(metric.outdoor_rate)}</td><td class="num">${formatPct(metric.retention_rate)}</td></tr>`;
  }).join("");
  const packTroop = council.pack_troop;
  return `<div class="council-detail">
    <div class="council-detail-grid">
      <section><h3>Membership</h3><div class="metric-stack">${membership}</div></section>
      <section><h3>Market and geography</h3><div class="metric-stack">${market}</div></section>
      <section><h3>BeAScout indicators</h3><div class="metric-stack">${pins}</div></section>
    </div>
    ${packTroop ? `<p class="muted">Packs and troops combined: ${formatNumber(packTroop.units)} units · ${formatNumber(packTroop.current_youth)} youth · ${changeRate(packTroop.yoy_pct)} YOY.</p>` : ""}
    <h3>Program Unit Metrics</h3>
    <p class="panel-intro">Program tabs use a separate population from membership totals above. Blank values remain unavailable.${printable ? "" : " Scroll the table for all measures."}</p>
    <div class="table-wrap program-table" tabindex="0" role="region" aria-label="Scrollable program metrics"><table><caption class="sr-only">Program Unit Metrics for ${escapeHtml(council.council)}</caption><thead><tr><th scope="col">Program</th><th scope="col" class="num">Units</th><th scope="col" class="num">Youth</th><th scope="col" class="num">YOY %</th><th scope="col" class="num">Avg metric</th><th scope="col" class="num">Metric 0–2</th><th scope="col" class="num">UL &amp; CC trained</th><th scope="col" class="num">Healthy size</th><th scope="col" class="num">Units growing</th><th scope="col" class="num">Advancement</th><th scope="col" class="num">Outdoor</th><th scope="col" class="num">Imported “retention”*</th></tr></thead><tbody>${programs}</tbody></table></div>
    <p class="metric-caveat">*Imported “retention” follows the workbook model; its cohort and measurement window are unverified. It is not a verified annual cohort-retention measure. Values above 100% are preserved.</p>
    ${printable ? "" : `<div class="board-actions"><a class="detail-link" href="index.html?council=${encodeURIComponent(council.council_number)}">Council overview</a><a class="detail-link" href="unit-health.html?council=${encodeURIComponent(council.council_number)}">Explore unit health</a><a class="detail-link" href="council-report.html?council=${encodeURIComponent(council.council_number)}">Print council report</a></div>`}
  </div>`;
}

function median(values) {
  const ordered = values.filter(Number.isFinite).sort((a, b) => a - b);
  const middle = Math.floor(ordered.length / 2);
  if (!ordered.length) return null;
  return ordered.length % 2 ? ordered[middle] : (ordered[middle - 1] + ordered[middle]) / 2;
}

function reportGeography(data, council, peers) {
  const split = (urban) => Number.isFinite(urban)
    ? `${formatPct(urban)} urban and ${formatPct(1 - urban)} rural` : "Unavailable";
  const census = peers.map((peer) => peer.urban_pct).filter(Number.isFinite);
  const snapshot = data.unitGeography;
  const unitRow = snapshot?.councils[council.council_number];
  const rural = ruralUnitShare(unitRow);
  const peerUnits = peers.map((peer) => snapshot?.councils[peer.council_number])
    .filter((row) => ruralUnitShare(row) != null);
  const peerRural = median(peerUnits.map(ruralUnitShare));
  const coverage = (count) => count < peers.length ? ` (${count} of ${peers.length} peers)` : "";
  const unitCoverage = rural == null ? "" : ` ${formatNumber(totalCounts(unitRow.matched))} of ${formatNumber(totalCounts(unitRow.units))} reported units classified for this council.`;
  const peerCoverage = peerUnits.map((row) => totalCounts(row.matched) / totalCounts(row.units));
  const coverageRange = peerCoverage.length
    ? ` Peer classification coverage ${formatPct(Math.min(...peerCoverage))}–${formatPct(Math.max(...peerCoverage))}.` : "";
  return `<h3>2020 Census population split</h3>
    <p><strong>Council</strong> ${split(council.urban_pct)}. <strong>Peer median</strong> ${split(median(census))}${coverage(census.length)}.</p>
    <h3>Units in majority-urban and majority-rural ZIP areas</h3>
    <p><strong>Council</strong> ${split(rural == null ? null : 1 - rural)}. <strong>Peer median</strong> ${split(peerRural == null ? null : 1 - peerRural)}${coverage(peerUnits.length)}.</p>
    <p class="muted">${snapshot ? `National Pin Data Report, ${escapeHtml(geographyDate(snapshot))}.${unitCoverage}${coverageRange} Shares use units classified in matched council ZIP areas.` : "Unit geography data is currently unavailable."}</p>`;
}

function initCouncilReport(data) {
  const number = getQueryCouncil();
  const council = data.councils.find((row) => row.council_number === number);
  if (!council) {
    document.getElementById("reportStatus").textContent = "Select a council from the CST Dashboard to open its report.";
    return;
  }
  const name = council.council.replace(/\s\d{3}$/, "");
  const peers = peerSet(data, council);
  const comparison = [council, ...peers].sort((a, b) => (b.yoy_pct ?? -Infinity) - (a.yoy_pct ?? -Infinity)
    || a.council.localeCompare(b.council));
  const fields = ["units", "current_youth", "tay", "yoy_pct", "year_end_pct", "tay_pct"];
  const formats = [formatNumber, formatNumber, formatNumber, formatSignedPct2, formatSignedPct2, formatPct2];
  const values = (record) => fields.map((field, i) => `<td class="num">${formats[i](record[field])}</td>`).join("");
  const benchmark = Object.fromEntries(fields.map((field) => [field, median(peers.map((peer) => peer[field]))]));
  const growthRank = 1 + peers.filter((peer) => peer.yoy_pct != null && peer.yoy_pct > council.yoy_pct).length;
  const ranked = comparison.filter((row) => row.yoy_pct != null).length;
  const missingTay = data.councils.filter((row) => !(row.tay > 0)).length;
  const sourceDate = dateFmt.format(new Date(data.metadata.source_downloaded_at));
  const brand = document.getElementById("reportBrand").innerHTML;
  const header = (subtitle, heading) => `<header class="report-header">
    <div class="report-brand">${brand}<span>Workbook downloaded ${escapeHtml(sourceDate)}</span></div>
    <${heading} class="report-name">${escapeHtml(name)}</${heading}><p>${subtitle}</p>
  </header>`;
  document.title = `${name} · Council Details and Peer Comparison`;
  document.getElementById("reportContent").innerHTML = `
    <article class="report-sheet">
      ${header(`Council details · Council ${escapeHtml(number)} · ${escapeHtml(cstLabel(council.cst ?? "unassigned"))}`, "h1")}
      ${cstCouncilDetail(data, council, true)}
      <p class="report-source">Source <a href="${escapeHtml(data.metadata.source_url)}">Councils Ranked.xlsx</a>. Membership cutoff date is unverified.</p>
    </article>
    <article class="report-sheet">
      ${header(`Peer comparison · ${peers.length} matched ${peers.length === 1 ? "council" : "councils"}`, "h2")}
      <p><strong>${formatNumber(council.current_youth)} primary youth</strong> · ${formatSigned(council.yoy_delta)} year over year (${formatSignedPct2(council.yoy_pct)}).${peers.length && council.yoy_pct != null ? ` It ranked ${growthRank} of ${ranked} on year-over-year growth.` : ""}</p>
      ${peers.length ? "" : "<p>No councils qualified under the workbook’s peer matching rule for this selection.</p>"}
      <div class="table-wrap report-peers" tabindex="0" role="region" aria-label="Peer membership and market reach">
        <table><thead><tr><th scope="col">Council</th><th scope="col" class="num">Units</th><th scope="col" class="num">Primary youth</th>
          <th scope="col" class="num">TAY</th><th scope="col" class="num">Youth YOY</th><th scope="col" class="num">vs. 2025 year-end</th><th scope="col" class="num">TAY share</th></tr></thead>
        <tbody>${comparison.map((row) => `<tr${row === council ? ' class="focus-row"' : ""}><th scope="row">${escapeHtml(row.council)}</th>${values(row)}</tr>`).join("")}</tbody>
        ${peers.length ? `<tfoot><tr><th scope="row">Peer median</th>${values(benchmark)}</tr></tfoot>` : ""}</table>
      </div>
      <div class="report-notes">
        ${reportGeography(data, council, peers)}
        <h3>How peers were matched</h3>
        <p>Peers have 80% to 120% of this council’s unit count, current primary youth and total available youth (TAY) on all three measures. The median excludes the selected council. ${formatNumber(missingTay)} of ${formatNumber(data.councils.length)} councils lacked a positive TAY value and could not qualify.</p>
      </div>
    </article>`;
  document.getElementById("reportStatus").hidden = true;
  const print = document.getElementById("printReport");
  print.disabled = false;
  print.addEventListener("click", () => window.print());
}

function cstGrowthRow(label, detail, value, maxAbs) {
  const width = value == null ? 0 : Math.abs(value) / maxAbs * 50;
  const left = value < 0 ? 50 - width : 50;
  return `<div class="chart-row cst-chart-row"><div class="chart-label">${escapeHtml(label)}<span>${escapeHtml(detail)}</span></div><div class="cst-growth-track" aria-hidden="true"><span class="${value < 0 ? "decline" : "increase"}" style="left:${left.toFixed(3)}%;width:${width.toFixed(3)}%"></span></div><strong class="bar-value ${classForValue(value)}">${formatSignedPct(value)}</strong></div>`;
}

function renderCst(data, selectedCst) {
  const search = document.getElementById("cstSearch").value.trim().toLowerCase();
  const scoped = data.councils.filter((row) => selectedCst === "all" || (row.cst == null ? "unassigned" : String(row.cst)) === selectedCst);
  const rows = scoped.filter((row) => !search || row.council.toLowerCase().includes(search) || row.council_number.includes(search));
  const summary = membershipSummary(rows);
  const groups = cstGroups(rows);
  const label = selectedCst === "all" ? "All CSTs" : cstLabel(selectedCst);
  document.getElementById("cstScope").textContent = `${label} · ${rows.length} of ${scoped.length} councils${search ? " match the search" : " in this view"}. Summaries and charts use the councils shown.`;
  document.getElementById("cstKpis").innerHTML = [
    kpiCard("Councils", formatNumber(summary.councils), `${groups.length} ${groups.length === 1 ? "territory" : "territories"} in view`),
    kpiCard("Current youth", formatNumber(summary.current_youth), `${formatSigned(summary.yoy_delta)} year over year`, tone(summary.yoy_pct)),
    kpiCard("YOY growth", formatSignedPct(summary.yoy_pct), `Prior youth: ${formatNumber(summary.prior_youth)}`, tone(summary.yoy_pct)),
    kpiCard("Total units", formatNumber(summary.units), unitBreakdown(summary)),
    kpiCard("Change since year-end", formatSignedPct(summary.year_end_pct), `${formatSigned(summary.year_end_delta)} since year-end 2025`, tone(summary.year_end_pct)),
    kpiCard("TAY penetration", formatPct(summary.tay_pct), `${summary.tay_covered_councils} of ${rows.length} councils with TAY`),
    kpiCard("TAY population", formatNumber(summary.tay), "Covered councils only"),
    kpiCard("Councils growing", formatNumber(rows.filter((row) => row.yoy_pct > 0).length), "Positive year-over-year membership growth"),
  ].join("");
  document.getElementById("cstChartTitle").textContent = selectedCst === "all" ? "Year-over-Year Growth by CST" : `${label} Council Growth`;
  const comparisons = selectedCst === "all"
    ? groups.map(([key, councils]) => ({ label: cstLabel(key), summary: membershipSummary(councils) }))
    : [...rows].sort((a, b) => (b.yoy_pct ?? -Infinity) - (a.yoy_pct ?? -Infinity) || a.council.localeCompare(b.council))
      .map((row) => ({ label: row.council, summary: row }));
  const maxAbs = Math.max(...comparisons.map((row) => Math.abs(row.summary.yoy_pct || 0)), .001);
  document.getElementById("cstGrowthChart").innerHTML = comparisons.length ? comparisons.map(({ label: name, summary: s }) => cstGrowthRow(name, `${formatNumber(s.current_youth)} youth · ${formatSigned(s.yoy_delta)} YOY`, s.yoy_pct, maxAbs)).join("") : '<div class="empty-state">No councils match this search.</div>';
  const sort = document.getElementById("cstSort").value;
  const sorters = {
    name: (a, b) => a.council.localeCompare(b.council),
    growth: (a, b) => (b.yoy_pct ?? -Infinity) - (a.yoy_pct ?? -Infinity) || a.council.localeCompare(b.council),
    youth: (a, b) => b.current_youth - a.current_youth || a.council.localeCompare(b.council),
  };
  document.getElementById("cstGroups").innerHTML = groups.length ? groups.map(([key, councils]) => {
    const total = membershipSummary(councils);
    return `<details class="territory-group"${selectedCst !== "all" || search ? " open" : ""}><summary class="territory-summary"><span><strong>${escapeHtml(cstLabel(key))}</strong><small>${councils.length} ${councils.length === 1 ? "council" : "councils"} · ${formatNumber(total.units)} units</small></span><span>${formatNumber(total.current_youth)} youth</span><span class="${classForValue(total.yoy_pct)}">${formatSignedPct(total.yoy_pct)} YOY</span></summary><div class="territory-councils">${[...councils].sort(sorters[sort]).map((council) => `<details class="council-record" data-council="${escapeHtml(council.council_number)}"><summary class="council-summary"><span class="council-name"><strong>${escapeHtml(council.council)}</strong><small>${formatNumber(council.units)} units · National YOY rank ${formatRank(council.yoy_rank)}</small></span><span>${formatNumber(council.current_youth)} youth</span><span class="${classForValue(council.yoy_pct)}">${formatSignedPct(council.yoy_pct)} YOY</span></summary>${cstCouncilDetail(data, council)}</details>`).join("")}</div></details>`;
  }).join("") : '<div class="empty-state">No councils match this search. Reset filters to restore this territory’s councils.</div>';
  const missingTay = rows.filter((row) => row.tay == null || row.tay <= 0);
  document.getElementById("cstSource").innerHTML = `${sourceLink(data)}<span>${escapeHtml(data.metadata.source_name)}, downloaded ${escapeHtml(dateFmt.format(new Date(data.metadata.source_downloaded_at)))}. CST assignments come from the council membership source. Growth uses summed current and baseline youth, not an average of council percentages. TAY penetration uses youth and TAY only from covered councils. ${missingTay.length ? `TAY unavailable for ${escapeHtml(missingTay.map((row) => row.council).join("; "))}.` : "All councils in this view have TAY coverage."} Rankings shown are national; program and PIN populations may differ from membership totals.</span>`;
}

function initCst(data) {
  const groups = cstGroups(data.councils);
  const requested = new URLSearchParams(window.location.search).get("cst");
  const selectedCst = requested === "all" || groups.some(([key]) => key === requested) ? requested : "all";
  const title = selectedCst === "all" ? "CST Dashboard" : `${cstLabel(selectedCst)} Dashboard`;
  document.getElementById("cstTitle").textContent = title;
  document.title = `${title} · Council Performance Rankings`;
  document.getElementById("cstSubtitle").textContent = selectedCst === "all"
    ? "Explore every territory, then expand its councils for membership and program details."
    : `Membership performance and council details for ${cstLabel(selectedCst)}.`;
  document.getElementById("cstLinks").innerHTML = [["all", data.councils], ...groups].map(([key, councils]) => `<a class="cst-link${selectedCst === key ? " selected" : ""}" href="cst.html?cst=${encodeURIComponent(key)}"${selectedCst === key ? ' aria-current="page"' : ""}><strong>${key === "all" ? "All CSTs" : escapeHtml(cstLabel(key))}</strong><span>${councils.length} ${councils.length === 1 ? "council" : "councils"}</span></a>`).join("");
  if (requested != null && requested !== selectedCst) {
    const notice = document.createElement("p");
    notice.className = "panel-intro";
    notice.textContent = "That CST is not in the current source. Showing all CSTs.";
    document.getElementById("cstLinks").before(notice);
  }
  document.getElementById("cstSearch").addEventListener("input", () => renderCst(data, selectedCst));
  document.getElementById("cstSort").addEventListener("change", () => renderCst(data, selectedCst));
  document.getElementById("cstReset").addEventListener("click", () => {
    document.getElementById("cstSearch").value = "";
    document.getElementById("cstSort").value = "name";
    renderCst(data, selectedCst);
  });
  for (const [id, open] of [["cstExpand", true], ["cstCollapse", false]]) {
    document.getElementById(id).addEventListener("click", () => document.querySelectorAll("#cstGroups details").forEach((detail) => { detail.open = open; }));
  }
  renderCst(data, selectedCst);
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
    const page = document.body.dataset.page;
    const [response, geography] = await Promise.all([
      fetch("data/latest.json", { cache: "no-store" }),
      ["overview", "unit-health", "council-report"].includes(page)
        ? fetch("data/unit-geography.json", { cache: "no-store" })
          .then((r) => r.ok ? r.json() : null).catch(() => null)
        : null,
    ]);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    updateSourceDates(data);
    data.unitGeography = geography;
    if (page === "overview") initOverview(data);
    if (page === "rankings") initRankings(data);
    if (page === "unit-health") initHealth(data);
    if (page === "about") initAbout(data);
    if (page === "cst") initCst(data);
    if (page === "council-report") initCouncilReport(data);
  } catch (error) {
    if (document.body.dataset.page === "council-report") document.getElementById("reportStatus").hidden = true;
    showError(error);
  }
}

main();
