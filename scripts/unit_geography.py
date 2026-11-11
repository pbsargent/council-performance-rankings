#!/usr/bin/env python3
"""Prepare and validate the public council/program aggregates from the reviewed comparison."""

import argparse
import json
import math
import re
from datetime import date
from pathlib import Path

ASSET = "data/unit-geography.json"
PROGRAMS = {"Cub Scouts", "Scouts BSA", "Venturing", "Sea Scouts", "Exploring", "Learning for Life (inferred)"}


def counts_ok(counts, size):
    return isinstance(counts, list) and len(counts) == size and all(type(n) is int and n >= 0 for n in counts)


def share_ok(value):
    return value is None or (type(value) in (float, int) and math.isfinite(value) and 0 <= value <= 1)


def validate(data):
    if set(data) != {"report_date", "councils"}:
        raise ValueError("Invalid unit geography snapshot fields")
    date.fromisoformat(data["report_date"])
    if not data["councils"]:
        raise ValueError("Empty unit geography snapshot")
    for number, row in data["councils"].items():
        if not re.fullmatch(r"[0-9]{3}", number) or set(row) != {"units", "matched", "residents_rural_zip", "census_urban", "programs"}:
            raise ValueError(f"Invalid unit geography council record: {number}")
        units, matched, programs = row["units"], row["matched"], row["programs"]
        rural, urban = row["residents_rural_zip"], row["census_urban"]
        if not counts_ok(units, 3) or not sum(units) or not share_ok(rural) or not share_ok(urban):
            raise ValueError(f"Invalid unit or population aggregates: {number}")
        if (rural is None) != (matched is None) or (matched is not None and (
            not counts_ok(matched, 2) or any(m > n for m, n in zip(matched, units))
        )):
            raise ValueError(f"Invalid matched ZIP aggregates: {number}")
        if not programs or set(programs) - PROGRAMS or any(not counts_ok(p, 3) for p in programs.values()):
            raise ValueError(f"Invalid program aggregates: {number}")
        if list(map(sum, zip(*programs.values()))) != units:
            raise ValueError(f"Program counts do not reconcile: {number}")


def build(source, report_date):
    councils = {}
    for number, _, _, urban, rural, unknown, census_urban, residents, matched_urban, matched_rural in source["councils"]:
        key = f"{number:03d}"
        if key in councils:
            raise ValueError(f"Duplicate council: {key}")
        councils[key] = {"units": [urban, rural, unknown], "matched": None if residents is None else [matched_urban, matched_rural],
                         "residents_rural_zip": residents, "census_urban": census_urban, "programs": {}}
    for number, _, program, urban, rural, unknown, *_ in source["programs"]:
        programs = councils[f"{number:03d}"]["programs"]
        if program in programs:
            raise ValueError(f"Duplicate council/program: {number} {program}")
        programs[program] = [urban, rural, unknown]
    data = {"report_date": report_date, "councils": councils}
    validate(data)
    eligible = [r for r in councils.values() if r["matched"] and sum(r["matched"]) * 10 >= sum(r["units"]) * 9]
    above = sum(r["matched"][1] / sum(r["matched"]) > r["residents_rural_zip"] for r in eligible)
    if [len(eligible), above] != [source["same_90"][0], source["same_90"][2]]:
        raise ValueError("National comparison does not reconcile to the reviewed analysis")
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--report-date", required=True)
    parser.add_argument("--output", type=Path, default=Path(ASSET))
    args = parser.parse_args()
    data = build(json.loads(args.comparison.read_text()), args.report_date)
    args.output.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
