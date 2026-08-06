#!/usr/bin/env python3
"""Profile the generated council-level dashboard data for trust and join risks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "latest.json")
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
            if record.get("units") is not None and total_buckets != record["units"]:
                count_reconciliation_issues.append({"program": program, "council": record["council"], "units": record["units"], "buckets": total_buckets})

    join_failures = {
        program: summary
        for program, summary in join_summary.items()
        if summary["missing_from_metrics"] or summary["metrics_without_ranking"]
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
            "medium",
            "Aggregate metric rates fall outside their expected 0–100% range",
            {"count": len(range_issues), "samples": range_issues[:20]},
            "Rate cards and comparisons may be misleading.",
            "Review the affected workbook formulas and source-unit values.",
        ))
    if count_reconciliation_issues:
        findings.append(issue(
            "medium",
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
            "medium",
            "Unit PIN rates fall outside 0–100%",
            {"count": len(pin_range_issues), "samples": pin_range_issues[:20]},
            "PIN readiness cards may be misleading.",
            "Review Unit_PIN aggregation formulas.",
        ))

    metric_all = data["program_summaries"]["All Units"]
    ranking_national = data["national"]
    unit_difference = metric_all["units"] - ranking_national["units"]
    youth_difference = metric_all["youth_current"] - ranking_national["current_youth"]
    findings.append(issue(
        "medium",
        "Membership ranking and unit-metric tabs do not share the same aggregate totals",
        {
            "ranking_units": ranking_national["units"],
            "unit_metric_units": metric_all["units"],
            "unit_difference": unit_difference,
            "ranking_current_youth": ranking_national["current_youth"],
            "unit_metric_current_youth": metric_all["youth_current"],
            "youth_difference": youth_difference,
        },
        "A viewer could incorrectly expect the Overview and Unit Health totals to reconcile.",
        "Keep the two grains visually separated and disclose that Unit Health uses the workbook's metric-tab population.",
    ))

    blocking = [finding for finding in findings if finding["severity"] in {"critical", "high"}]
    report = {
        "status": "pass_with_documented_caveat" if not blocking else "fail",
        "dataset": {
            "source": data["metadata"]["source_name"],
            "grain": "one row per council on rankings; one row per council and program on unit metrics",
            "council_rows": len(councils),
            "unique_council_numbers": len(set(council_numbers)),
            "source_downloaded_at": data["metadata"]["source_downloaded_at"],
        },
        "checks": {
            "identifier_uniqueness": "pass" if not duplicate_numbers else "fail",
            "core_count_validity": "pass" if not invalid_core else "fail",
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
