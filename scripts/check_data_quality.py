#!/usr/bin/env python3
"""Profile the generated council-level dashboard data for trust and join risks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from build_site import XlsxReader, count_unit_exclusions


ROOT = Path(__file__).resolve().parents[1]
RATE_FIELDS = [
    "metric_low_rate",
    "metric_mid_rate",
    "metric_high_rate",
    "trained_rate",
    "healthy_size_rate",
    "membership_growth_unit_rate",
    "advancement_rate",
    "outdoor_rate",
]
PIN_RATE_FIELDS = [
    "pin_active_rate",
    "apply_active_rate",
    "fundraising_active_rate",
    "trial_visit_rate",
    "unit_fee_rate",
    "updated_in_year_rate",
    "meeting_day_rate",
]


def issue(severity: str, finding: str, evidence: dict[str, Any], impact: str, remediation: str) -> dict[str, Any]:
    return {
        "severity": severity,
        "finding": finding,
        "evidence": evidence,
        "impact": impact,
        "remediation": remediation,
    }


def reconcile_units(data: dict[str, Any], reader: XlsxReader) -> dict[str, Any]:
    ranking_units = {row["council"]: row["units"] for row in data["councils"]}
    metric_units = {row["council"]: row["units"] for row in data["unit_metrics"]["All Units"]}
    clubs, coming, overlap = count_unit_exclusions(reader, ranking_units)
    rows = []
    for council, total in ranking_units.items():
        expected = total - clubs[council] - coming[council] + overlap[council]
        actual = metric_units[council]
        rows.append({
            "council": council,
            "ranking_units": total,
            "clubs": clubs[council],
            "coming_units": coming[council],
            "coming_clubs": overlap[council],
            "expected_unit_metric_units": expected,
            "unit_metric_units": actual,
            "remaining_gap": expected - actual,
        })
    gaps = [row for row in rows if row["remaining_gap"]]
    return {
        "ranking_units": sum(ranking_units.values()),
        "unit_metric_units": sum(metric_units.values()),
        "clubs": sum(clubs.values()),
        "coming_units": sum(coming.values()),
        "coming_clubs": sum(overlap.values()),
        "remaining_gap": sum(row["remaining_gap"] for row in rows),
        "councils_with_gap": len(gaps),
        "council_gaps": gaps,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "latest.json")
    parser.add_argument("--source", type=Path, help="Matching private workbook for club and Coming unit reconciliation")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    councils = data["councils"]
    council_names = {record["council"] for record in councils}
    council_numbers = [record["council_number"] for record in councils]
    findings: list[dict[str, Any]] = []

    duplicate_numbers = sorted({number for number in council_numbers if council_numbers.count(number) > 1})
    if duplicate_numbers:
        findings.append(issue(
            "high",
            "Council number is not unique at the ranking grain",
            {"duplicate_numbers": duplicate_numbers},
            "Council selection and joins could resolve to the wrong row.",
            "Correct duplicate council identifiers in the source workbook before publishing.",
        ))

    invalid_core = [
        record["council"]
        for record in councils
        if any(record.get(field) is None or record[field] < 0 for field in ["units", "current_youth", "prior_youth", "year_end_youth"])
    ]
    if invalid_core:
        findings.append(issue(
            "high",
            "Core count fields are missing or negative",
            {"councils": invalid_core[:20], "count": len(invalid_core)},
            "Membership totals and rankings would be unreliable.",
            "Repair the affected source rows and regenerate the site.",
        ))

    tay_missing = [record["council"] for record in councils if record.get("tay") in (None, 0)]
    tay_rate_issues = [
        {"council": record["council"], "tay_pct": record.get("tay_pct")}
        for record in councils
        if record.get("tay") not in (None, 0) and (record.get("tay_pct") is None or not 0 <= record["tay_pct"] <= 1)
    ]
    if tay_rate_issues:
        findings.append(issue(
            "high",
            "TAY penetration is missing or outside its expected 0–100% range",
            {"count": len(tay_rate_issues), "samples": tay_rate_issues[:20]},
            "TAY comparisons and peer matching would be unreliable.",
            "Review the TAY and current-youth values in the Councils worksheet.",
        ))
    if tay_missing:
        findings.append(issue(
            "medium",
            "TAY is unavailable for a subset of council rows",
            {"count": len(tay_missing), "councils": tay_missing},
            "Those councils cannot have a TAY penetration rate, TAY rank, or TAY-matched peers.",
            "Preserve the source blanks and limit TAY comparisons to councils with a supplied TAY value.",
        ))

    join_summary = {}
    range_issues = []
    count_reconciliation_issues = []
    for program, records in data["unit_metrics"].items():
        names = {record["council"] for record in records}
        join_summary[program] = {
            "rows": len(records),
            "matched_to_rankings": len(names & council_names),
            "missing_from_metrics": sorted(council_names - names),
            "metrics_without_ranking": sorted(names - council_names),
            "duplicate_rows": len(records) - len(names),
        }
        for record in records:
            for field in RATE_FIELDS:
                value = record.get(field)
                if value is not None and not 0 <= value <= 1:
                    range_issues.append({"program": program, "council": record["council"], "field": field, "value": value})
            average = record.get("average_metric")
            if average is not None and not 0 <= average <= 5:
                range_issues.append({"program": program, "council": record["council"], "field": "average_metric", "value": average})
            total_buckets = sum(record.get(field) or 0 for field in ["metric_low_count", "metric_mid_count", "metric_high_count"])
            if record.get("units") is None or total_buckets != record["units"]:
                count_reconciliation_issues.append({"program": program, "council": record["council"], "units": record["units"], "buckets": total_buckets})

    join_failures = {
        program: summary
        for program, summary in join_summary.items()
        if summary["missing_from_metrics"] or summary["metrics_without_ranking"] or summary["duplicate_rows"]
    }
    if join_failures:
        findings.append(issue(
            "high",
            "Council joins do not fully cover the unit-metric tabs",
            join_failures,
            "Selected-council unit health may be blank or attached to the wrong council.",
            "Normalize council names and identifiers in the source workbook.",
        ))
    if range_issues:
        findings.append(issue(
            "high",
            "Aggregate metric rates fall outside their expected 0–100% range",
            {"count": len(range_issues), "samples": range_issues[:20]},
            "Rate cards and comparisons may be misleading.",
            "Review the affected workbook formulas and source-unit values.",
        ))
    if count_reconciliation_issues:
        findings.append(issue(
            "high",
            "Unit metric buckets do not sum to the reported unit count",
            {"count": len(count_reconciliation_issues), "samples": count_reconciliation_issues[:20]},
            "The health-mix chart could understate or overstate a category.",
            "Reconcile bucket formulas to the unit population.",
        ))

    pin_range_issues = []
    for record in (item.get("pin") for item in councils):
        if not record:
            continue
        for field in PIN_RATE_FIELDS:
            value = record.get(field)
            if value is not None and not 0 <= value <= 1:
                pin_range_issues.append({"council": record["council"], "field": field, "value": value})
    if pin_range_issues:
        findings.append(issue(
            "high",
            "Unit PIN rates fall outside 0–100%",
            {"count": len(pin_range_issues), "samples": pin_range_issues[:20]},
            "PIN readiness cards may be misleading.",
            "Review Unit_PIN aggregation formulas.",
        ))

    metric_all = data["program_summaries"]["All Units"]
    ranking_national = data["national"]
    youth_counts = {
        "primary_youth": ranking_national["current_youth"],
        "total_youth": metric_all["youth_current"],
    }
    unit_reconciliation = None
    if args.source:
        if hashlib.sha256(args.source.read_bytes()).hexdigest() != data["metadata"].get("source_sha256"):
            parser.error("Workbook SHA-256 does not match the dashboard payload")
        if not (join_failures or invalid_core or count_reconciliation_issues):
            reader = XlsxReader(args.source)
            try:
                unit_reconciliation = reconcile_units(data, reader)
            finally:
                reader.close()
            if unit_reconciliation["councils_with_gap"]:
                findings.append(issue(
                    "medium",
                    "Some council unit totals differ after excluding clubs and Coming units",
                    unit_reconciliation,
                    "Offsetting council gaps can cancel out in the national total.",
                    "Review the affected councils in the private reconciliation and disclose the remaining gap.",
                ))
    elif ranking_national["units"] != metric_all["units"]:
        findings.append(issue(
            "medium",
            "Ranking and Unit Metrics totals differ; source reconciliation was not run",
            {"ranking_units": ranking_national["units"], "unit_metric_units": metric_all["units"]},
            "The payload alone cannot explain which units are excluded.",
            "Run the checker with --source and the matching private workbook.",
        ))

    blocking = [finding for finding in findings if finding["severity"] in {"critical", "high"}]
    report = {
        "status": "fail" if blocking else "pass_with_documented_caveat" if findings else "pass",
        "dataset": {
            "source": data["metadata"]["source_name"],
            "grain": "one row per council on rankings; one row per council and program on unit metrics",
            "council_rows": len(councils),
            "unique_council_numbers": len(set(council_numbers)),
            "source_downloaded_at": data["metadata"]["source_downloaded_at"],
        },
        "unit_reconciliation": unit_reconciliation,
        "youth_counts": youth_counts,
        "checks": {
            "identifier_uniqueness": "pass" if not duplicate_numbers else "fail",
            "core_count_validity": "pass" if not invalid_core else "fail",
            "tay_penetration_validity": "pass" if not tay_rate_issues else "fail",
            "tay_coverage": {"covered_councils": len(councils) - len(tay_missing), "missing_councils": tay_missing},
            "unit_metric_join_coverage": join_summary,
            "unit_metric_range_issues": len(range_issues),
            "unit_bucket_reconciliation_issues": len(count_reconciliation_issues),
            "pin_range_issues": len(pin_range_issues),
        },
        "findings": findings,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 1 if blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
