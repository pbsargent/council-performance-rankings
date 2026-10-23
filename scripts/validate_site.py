#!/usr/bin/env python3
"""Validate candidate data, aggregate-only schema, brand assets, and system themes."""

import argparse
import hashlib
import json
import math
import re
from pathlib import Path

from build_site import SOURCE_WORKBOOK_URL
from source_contract import PROGRAM_SHEETS

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "rankings.html", "unit-health.html", "about.html"]
REQUIRED = [*PAGES, "assets/dashboard.css", "assets/dashboard.js", "assets/scouting-america-signature.png", ".nojekyll"]
COUNCIL = set("cst council council_number units current_youth prior_youth yoy_delta yoy_pct yoy_rank year_end_youth year_end_delta year_end_pct year_end_rank tay tay_pct tay_rank".split())
PIN = set("council council_number units pin_active_rate apply_active_rate fundraising_active_rate trial_visit_rate unit_fee_rate updated_in_year_rate meeting_day_rate".split())
METRIC = set("program council council_number units average_metric metric_low_count metric_mid_count metric_high_count metric_low_rate metric_mid_rate metric_high_rate trained_rate healthy_size_rate membership_growth_unit_rate advancement_rate outdoor_rate retention_rate youth_current youth_prior youth_delta youth_growth_rate".split())
SUMMARY = (METRIC - {"council", "council_number", "metric_low_rate", "metric_mid_rate", "metric_high_rate"}) | {"councils"}
NATIONAL = set("council_count units current_youth prior_youth yoy_delta yoy_pct year_end_youth year_end_delta year_end_pct tay tay_current_youth tay_pct tay_covered_councils positive_growth_councils".split())
METADATA = set("title source_name source_url source_sha256 source_downloaded_at generated_at selected_council methodology_version privacy".split())
SIGNATURE_SHA256 = "d8e9ba549e2b434dbe3d57b9e43d8a060c5d6a5f0a63d6d0dcd3bc5b84e2c2b3"


def competition_ranks(records, field):
    ordered = sorted((r for r in records if r.get(field) is not None), key=lambda r: (-r[field], r["council"]))
    ranks, last, rank = {}, None, 0
    for index, record in enumerate(ordered, 1):
        if last is None or not math.isclose(record[field], last, rel_tol=1e-12, abs_tol=1e-12):
            rank, last = index, record[field]
        ranks[record["council"]] = rank
    return ranks


def validate(data, root=ROOT):
    failures = []

    def keys(record, allowed, path, required=()):
        if not isinstance(record, dict):
            raise ValueError(f"Expected object at {path}")
        unexpected, missing = set(record) - allowed, set(required) - record.keys()
        if unexpected or missing:
            failures.append(f"Aggregate schema mismatch at {path}: unexpected {sorted(unexpected)}, missing {sorted(missing)}")

    def scalars(record, strings, containers, path):
        for key, value in record.items():
            if key in containers:
                continue
            valid = isinstance(value, str) if key in strings else (value is None or (type(value) in (int, float) and math.isfinite(value)))
            if not valid:
                failures.append(f"Non-scalar or invalid aggregate value: {path}.{key}")

    def council(record, path, selected=False, nested=False):
        allowed = COUNCIL | (set() if nested else {"pin", "pack_troop"})
        if selected:
            allowed |= {"unit_metrics", "peer_count"}
        keys(record, allowed, path, {"council", "council_number", "units", "current_youth", "tay", "tay_pct"})
        scalars(record, {"council", "council_number"}, {"pin", "pack_troop", "unit_metrics"}, path)
        if record.get("pin") is not None:
            keys(record["pin"], PIN, path + ".pin", PIN)
            scalars(record["pin"], {"council", "council_number"}, set(), path + ".pin")
        if record.get("pack_troop") is not None:
            council(record["pack_troop"], path + ".pack_troop", nested=True)
        if selected:
            keys(record["unit_metrics"], set(PROGRAM_SHEETS), path + ".unit_metrics", PROGRAM_SHEETS)
            for program, metric in record["unit_metrics"].items():
                if metric is not None:
                    keys(metric, METRIC, path + ".unit_metrics." + program, METRIC)
                    scalars(metric, {"program", "council", "council_number"}, set(), path + ".unit_metrics." + program)

    top = set("metadata national selected peers councils program_summaries unit_metrics top_growth largest_councils".split())
    keys(data, top, "root", top)
    keys(data["metadata"], METADATA, "metadata")
    scalars(data["metadata"], METADATA, set(), "metadata")
    keys(data["national"], NATIONAL, "national", NATIONAL)
    scalars(data["national"], set(), set(), "national")
    for key in ("councils", "peers", "top_growth", "largest_councils"):
        for index, record in enumerate(data[key]):
            council(record, f"{key}[{index}]")
    council(data["selected"], "selected", selected=True)
    for key in ("unit_metrics", "program_summaries"):
        keys(data[key], set(PROGRAM_SHEETS), key, PROGRAM_SHEETS)
    for program, records in data["unit_metrics"].items():
        for index, record in enumerate(records):
            keys(record, METRIC, f"unit_metrics.{program}[{index}]", METRIC)
            scalars(record, {"program", "council", "council_number"}, set(), f"unit_metrics.{program}[{index}]")
        keys(data["program_summaries"][program], SUMMARY, f"program_summaries.{program}", SUMMARY)
        scalars(data["program_summaries"][program], {"program"}, set(), f"program_summaries.{program}")
    serialized = json.dumps(data, allow_nan=False)
    if any(token in serialized for token in ("/Users/", "file://", "/private/")):
        failures.append("Payload exposes a local filesystem path")
    if data["metadata"].get("source_url") != SOURCE_WORKBOOK_URL or data["metadata"].get("source_name") != "Councils Ranked.xlsx":
        failures.append("Source is not the exact canonical workbook")
    councils = data["councils"]
    names = {r["council"] for r in councils}
    if len(names) != len(councils) or not 200 <= len(councils) <= 300:
        failures.append("Council population is duplicated or outside 200–300")
    selected = data["selected"]
    if selected["council"] != data["metadata"]["selected_council"] or selected["council"] not in names:
        failures.append("Selected council mismatch")
    for field, output in (("yoy_pct", "yoy_rank"), ("year_end_pct", "year_end_rank"), ("tay_pct", "tay_rank")):
        expected = competition_ranks(councils, field)
        for record in councils:
            if record.get(output) != expected.get(record["council"]):
                failures.append(f"{output} mismatch: {record['council']}")
    for record in councils:
        for field, num, denom in (("yoy_pct", "yoy_delta", "prior_youth"), ("year_end_pct", "year_end_delta", "year_end_youth"), ("tay_pct", "current_youth", "tay")):
            expected = record[num] / record[denom] if record.get(denom) else None
            actual = record.get(field)
            if (expected is None) != (actual is None) or (expected is not None and not math.isclose(expected, actual, rel_tol=1e-12, abs_tol=1e-12)):
                failures.append(f"{field} mismatch: {record['council']}")
        if record["yoy_delta"] != record["current_youth"] - record["prior_youth"]:
            failures.append(f"YOY delta mismatch: {record['council']}")
    expected_peers = {r["council"] for r in councils if r["council"] != selected["council"]
                      and all(selected.get(f) and r.get(f) is not None and 0.8 <= r[f] / selected[f] <= 1.2 for f in ("units", "current_youth", "tay"))}
    if expected_peers != {r["council"] for r in data["peers"]} or len(data["peers"]) != len(expected_peers) or selected["peer_count"] != len(expected_peers):
        failures.append("Peer set does not match ±20% units/youth/TAY rule")
    national = data["national"]
    for field in ("units", "current_youth", "prior_youth", "year_end_youth"):
        if national[field] != sum(r[field] for r in councils):
            failures.append(f"National {field} total mismatch")
    covered = [r for r in councils if r.get("tay") not in (None, 0)]
    if national["council_count"] != len(councils) or national["tay_covered_councils"] != len(covered) or national["tay"] != sum(r["tay"] for r in covered) or national["tay_current_youth"] != sum(r["current_youth"] for r in covered):
        failures.append("National population or TAY coverage mismatch")
    for relative in REQUIRED:
        if not (root / relative).is_file():
            failures.append(f"Missing required file: {relative}")
    for name in PAGES:
        text = (root / name).read_text(encoding="utf-8")
        if text.count("<main") != 1 or text.count("</main>") != 1 or not re.search(r'<meta name="viewport"', text):
            failures.append(f"Malformed page structure: {name}")
        if 'assets/scouting-america-signature.png' not in text or 'aria-current="page"' not in text:
            failures.append(f"Brand signature or active navigation missing: {name}")
        if "/Users/" in text or "file://" in text:
            failures.append(f"HTML exposes a local path: {name}")
    css = (root / "assets/dashboard.css").read_text(encoding="utf-8")
    for token in ("prefers-color-scheme: dark", "color-scheme: light dark", "#003F87", "#CE1126", "#D6CEBD", "#232528", "#9AB3D5", "Arial"):
        if token not in css:
            failures.append(f"Brand/system theme contract missing: {token}")
    signature = root / "assets/scouting-america-signature.png"
    if signature.exists() and hashlib.sha256(signature.read_bytes()).hexdigest() != SIGNATURE_SHA256:
        failures.append("Scouting America signature artwork changed; verify against supplied guide")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/latest.json")
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        failures = validate(data)
        result = {"status": "fail" if failures else "pass", "councils": len(data["councils"]), "selected": data["selected"]["council"], "peers": len(data["peers"]), "failures": failures}
    except (KeyError, TypeError, ValueError, OSError) as error:
        result = {"status": "fail", "failures": [str(error)]}
    print(json.dumps(result, indent=2))
    return int(result["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
