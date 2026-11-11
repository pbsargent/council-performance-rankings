"use strict";

// Calculation and scope regressions using the same JS shipped to the browser.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "..");
const source = fs.readFileSync(path.join(root, "assets/dashboard.js"), "utf8").replace(/\nmain\(\);\s*$/, "");
const elements = new Map();
const context = vm.createContext({ Intl, URL, URLSearchParams,
  document: { getElementById(id) { if (!elements.has(id)) elements.set(id, { value: "", innerHTML: "", textContent: "" }); return elements.get(id); } },
});
vm.runInContext(source, context);
const data = JSON.parse(fs.readFileSync(path.join(root, "data/latest.json"), "utf8"));
const plain = (value) => JSON.parse(JSON.stringify(value));

test("CSTs partition all source councils once and reconcile to national totals", () => {
  const groups = context.cstGroups(data.councils);
  const councils = groups.flatMap(([, rows]) => rows);
  assert.equal(councils.length, data.councils.length);
  assert.equal(new Set(councils.map((row) => row.council_number)).size, councils.length);
  for (const [key, rows] of groups) assert.ok(rows.every((row) => String(row.cst) === key));
  const summary = context.membershipSummary(councils);
  for (const field of ["current_youth", "prior_youth", "units", "year_end_youth", "yoy_delta", "yoy_pct", "year_end_pct", "tay", "tay_pct", "tay_covered_councils"]) {
    assert.ok(Math.abs(summary[field] - data.national[field]) < 1e-9, field);
  }
  const totals = groups.map(([, rows]) => context.membershipSummary(rows));
  assert.equal(totals.reduce((sum, row) => sum + row.current_youth, 0), data.national.current_youth);
});

test("growth is recomputed from counts and TAY excludes uncovered youth", () => {
  const rows = [
    { current_youth: 20, prior_youth: 10, year_end_youth: 20, units: 1, tay: 100 },
    { current_youth: 90, prior_youth: 100, year_end_youth: 100, units: 10, tay: null },
  ];
  const summary = context.membershipSummary(rows);
  assert.equal(summary.yoy_pct, 0); // Not the 45% mean of +100% and -10%.
  assert.equal(summary.tay_pct, .2); // Not 110 / 100.
  assert.equal(summary.tay_covered_councils, 1);
  assert.equal(summary.units, 11);
});

test("empty, missing baseline and zero denominators remain undefined", () => {
  for (const rows of [[], [{ current_youth: 0, prior_youth: 0, year_end_youth: 0, units: 0, tay: null }], [{ current_youth: 4, prior_youth: null, year_end_youth: null, units: 1, tay: 0 }], [{ current_youth: null, prior_youth: 10, year_end_youth: 10, units: 1, tay: null }]]) {
    const summary = context.membershipSummary(rows);
    assert.equal(summary.yoy_pct, null);
    assert.equal(summary.year_end_pct, null);
    assert.equal(summary.tay_pct, null);
  }
  assert.equal(context.membershipSummary([]).current_youth, null);
});

test("new source CSTs and unassigned councils do not disappear", () => {
  assert.deepEqual(plain(context.cstGroups([{ cst: 21 }, { cst: null }, { cst: 3 }] )).map(([key]) => key), ["3", "21", "unassigned"]);
});

test("Coming unit totals use the visible councils and distinguish missing coverage from zero", () => {
  const rows = [{ units: 100, coming_units: 2 }, { units: 50, coming_units: 0 }];
  assert.equal(context.unitBreakdown(context.membershipSummary(rows)), "148 chartered · 2 Coming");
  assert.equal(context.unitBreakdown(context.membershipSummary(rows.slice(1))), "50 chartered · 0 Coming");
  assert.match(context.unitBreakdown(context.membershipSummary([...rows, { units: 10 }])), /unavailable/);
  assert.match(context.unitBreakdown(context.membershipSummary([])), /unavailable/);
});

test("search scopes totals, chart and details together and reset restores the CST", () => {
  const before = JSON.stringify(data);
  elements.set("cstSearch", { value: "564" });
  elements.set("cstSort", { value: "name" });
  context.renderCst(data, "7");
  const focus = data.councils.find((row) => row.council_number === "564");
  assert.match(elements.get("cstScope").textContent, /1 of 14 councils/);
  assert.match(elements.get("cstGroups").innerHTML, /data-council="564"/);
  assert.equal((elements.get("cstGroups").innerHTML.match(/data-council=/g) || []).length, 1);
  assert.match(elements.get("cstKpis").innerHTML, new RegExp(focus.current_youth.toLocaleString("en-US")));
  assert.match(elements.get("cstGrowthChart").innerHTML, /Capitol Area/);
  elements.get("cstSearch").value = "no such council";
  context.renderCst(data, "7");
  assert.match(elements.get("cstGroups").innerHTML, /No councils match/);
  assert.match(elements.get("cstGrowthChart").innerHTML, /No councils match/);
  elements.get("cstSearch").value = "";
  context.renderCst(data, "7");
  assert.equal((elements.get("cstGroups").innerHTML.match(/data-council=/g) || []).length, data.councils.filter((row) => row.cst === 7).length);
  assert.equal(JSON.stringify(data), before);
});

test("council program details preserve above-100 and blank imported values", () => {
  const council = data.councils[0];
  const fixture = { unit_metrics: { Ships: [{ council_number: council.council_number, retention_rate: 1.5 }] } };
  assert.match(context.cstCouncilDetail(fixture, council), /150\.0%/);
  fixture.unit_metrics.Ships[0].retention_rate = null;
  assert.doesNotMatch(context.cstCouncilDetail(fixture, council), /150\.0%/);
  assert.match(context.cstCouncilDetail(fixture, council), /window are unverified/);
  fixture.unit_metrics.Ships = [];
  assert.match(context.cstCouncilDetail(fixture, council), /No metric record available/);
});
