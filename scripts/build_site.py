#!/usr/bin/env python3
"""Build the static council-ranking data payload from the source workbook."""

from __future__ import annotations

import argparse
import json
import math
import re
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"x": MAIN, "r": REL}
CHICAGO = ZoneInfo("America/Chicago")


def q(tag: str) -> str:
    return f"{{{MAIN}}}{tag}"


def column_number(cell_ref: str) -> int:
    letters = re.match(r"[A-Z]+", cell_ref)
    if not letters:
        raise ValueError(f"Invalid cell reference: {cell_ref}")
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - 64
    return result


def clean_number(value: Any) -> float | int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return int(number) if number.is_integer() else number


def ratio(delta: Any, baseline: Any) -> float | None:
    delta_num = clean_number(delta)
    base_num = clean_number(baseline)
    if delta_num is None or base_num in (None, 0):
        return None
    return float(delta_num) / float(base_num)


def rank_desc(records: list[dict[str, Any]], field: str, output_field: str) -> None:
    ordered = sorted(
        (record for record in records if record.get(field) is not None),
        key=lambda record: (-record[field], record["council"]),
    )
    prior_value: float | None = None
    prior_rank = 0
    for index, record in enumerate(ordered, 1):
        value = record[field]
        if prior_value is None or not math.isclose(value, prior_value, rel_tol=1e-12, abs_tol=1e-12):
            prior_rank = index
            prior_value = value
        record[output_field] = prior_rank


class XlsxReader:
    def __init__(self, path: Path):
        self.path = path
        self.archive = zipfile.ZipFile(path)
        self.shared = self._shared_strings()
        self.sheets = self._sheet_parts()

    def close(self) -> None:
        self.archive.close()

    def _shared_strings(self) -> list[str]:
        try:
            root = ET.fromstring(self.archive.read("xl/sharedStrings.xml"))
        except KeyError:
            return []
        return ["".join(node.text or "" for node in item.iter(q("t"))) for item in root.findall(q("si"))]

    def _sheet_parts(self) -> dict[str, str]:
        workbook = ET.fromstring(self.archive.read("xl/workbook.xml"))
        relationships = ET.fromstring(self.archive.read("xl/_rels/workbook.xml.rels"))
        targets = {
            item.attrib["Id"]: item.attrib["Target"]
            for item in relationships.findall(f"{{{PKG_REL}}}Relationship")
        }
        parts: dict[str, str] = {}
        sheets_node = workbook.find("x:sheets", NS)
        if sheets_node is None:
            raise RuntimeError("Workbook has no worksheet collection")
        for sheet in sheets_node:
            target = targets[sheet.attrib[f"{{{REL}}}id"]]
            parts[sheet.attrib["name"]] = target.lstrip("/") if target.startswith("/") else f"xl/{target.lstrip('/')}"
        return parts

    def _cell_value(self, cell: ET.Element) -> Any:
        cell_type = cell.attrib.get("t")
        value_node = cell.find(q("v"))
        inline_node = cell.find(q("is"))
        if inline_node is not None:
            return "".join(node.text or "" for node in inline_node.iter(q("t")))
        if value_node is None or value_node.text is None:
            return None
        raw = value_node.text
        if cell_type == "s":
            index = int(raw)
            return self.shared[index] if 0 <= index < len(self.shared) else None
        if cell_type == "b":
            return raw == "1"
        if cell_type in {"str", "e"}:
            return raw
        number = clean_number(raw)
        return number if number is not None else raw

    def rows(self, sheet_name: str) -> Iterable[tuple[int, dict[int, Any]]]:
        part = self.sheets[sheet_name]
        with self.archive.open(part) as handle:
            for event, element in ET.iterparse(handle, events=("end",)):
                if element.tag == q("row"):
                    row_number = int(element.attrib.get("r", "0"))
                    values: dict[int, Any] = {}
                    for cell in element.findall(q("c")):
                        ref = cell.attrib.get("r")
                        if ref:
                            values[column_number(ref)] = self._cell_value(cell)
                    yield row_number, values
                    element.clear()


def extract_councils(reader: XlsxReader, sheet_name: str) -> tuple[list[dict[str, Any]], str | None]:
    records: list[dict[str, Any]] = []
    selected: str | None = None
    for row_number, cells in reader.rows(sheet_name):
        if row_number == 67 and isinstance(cells.get(17), str):
            selected = cells[17].strip()
        if row_number < 3:
            continue
        council = cells.get(2)
        if not isinstance(council, str) or not re.search(r"\d{3}$", council.strip()):
            continue
        current = clean_number(cells.get(4))
        prior = clean_number(cells.get(5))
        year_end = clean_number(cells.get(9))
        units = clean_number(cells.get(3))
        if current is None or prior is None or units is None:
            continue
        yoy_delta = current - prior
        ye_delta = current - year_end if year_end is not None else None
        council_number = re.search(r"(\d{3})$", council.strip()).group(1)
        records.append(
            {
                "cst": clean_number(cells.get(1)),
                "council": council.strip(),
                "council_number": council_number,
                "units": units,
                "current_youth": current,
                "prior_youth": prior,
                "yoy_delta": yoy_delta,
                "yoy_pct": ratio(yoy_delta, prior),
                "year_end_youth": year_end,
                "year_end_delta": ye_delta,
                "year_end_pct": ratio(ye_delta, year_end),
            }
        )
    rank_desc(records, "yoy_pct", "yoy_rank")
    rank_desc(records, "year_end_pct", "year_end_rank")
    return records, selected


def extract_unit_metrics(reader: XlsxReader, sheet_name: str, program: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row_number, cells in reader.rows(sheet_name):
        if row_number < 2:
            continue
        council = cells.get(2)
        if not isinstance(council, str) or not re.search(r"\d{3}$", council.strip()):
            continue
        youth_current = clean_number(cells.get(21))
        youth_prior = clean_number(cells.get(22))
        youth_delta = None if youth_current is None or youth_prior is None else youth_current - youth_prior
        records.append(
            {
                "program": program,
                "council": council.strip(),
                "council_number": re.search(r"(\d{3})$", council.strip()).group(1),
                "units": clean_number(cells.get(3)),
                "average_metric": clean_number(cells.get(4)),
                "metric_low_count": clean_number(cells.get(6)),
                "metric_mid_count": clean_number(cells.get(7)),
                "metric_high_count": clean_number(cells.get(8)),
                "metric_low_rate": clean_number(cells.get(10)),
                "metric_mid_rate": clean_number(cells.get(11)),
                "metric_high_rate": clean_number(cells.get(12)),
                "trained_rate": clean_number(cells.get(14)),
                "healthy_size_rate": clean_number(cells.get(15)),
                "membership_growth_unit_rate": clean_number(cells.get(16)),
                "advancement_rate": clean_number(cells.get(17)),
                "outdoor_rate": clean_number(cells.get(18)),
                "retention_rate": clean_number(cells.get(19)),
                "youth_current": youth_current,
                "youth_prior": youth_prior,
                "youth_delta": youth_delta,
                "youth_growth_rate": ratio(youth_delta, youth_prior),
            }
        )
    return records


def extract_pin(reader: XlsxReader) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row_number, cells in reader.rows("Unit_PIN"):
        if row_number < 2:
            continue
        council = cells.get(2)
        if not isinstance(council, str) or not re.search(r"\d{3}$", council.strip()):
            continue
        records.append(
            {
                "council": council.strip(),
                "council_number": re.search(r"(\d{3})$", council.strip()).group(1),
                "units": clean_number(cells.get(3)),
                "pin_active_rate": clean_number(cells.get(4)),
                "apply_active_rate": clean_number(cells.get(5)),
                "fundraising_active_rate": clean_number(cells.get(6)),
                "trial_visit_rate": clean_number(cells.get(7)),
                "unit_fee_rate": clean_number(cells.get(8)),
                "updated_in_year_rate": clean_number(cells.get(9)),
                "meeting_day_rate": clean_number(cells.get(10)),
            }
        )
    return records


def sum_numbers(records: list[dict[str, Any]], field: str) -> float | int:
    total = sum(float(record[field]) for record in records if record.get(field) is not None)
    return int(total) if total.is_integer() else total


def weighted_average(records: list[dict[str, Any]], value_field: str, weight_field: str) -> float | None:
    pairs = [
        (float(record[value_field]), float(record[weight_field]))
        for record in records
        if record.get(value_field) is not None and record.get(weight_field) not in (None, 0)
    ]
    denominator = sum(weight for _, weight in pairs)
    return sum(value * weight for value, weight in pairs) / denominator if denominator else None


def summarize_program(program: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    units = sum_numbers(records, "units")
    current = sum_numbers(records, "youth_current")
    prior = sum_numbers(records, "youth_prior")
    delta = current - prior
    return {
        "program": program,
        "councils": len(records),
        "units": units,
        "average_metric": weighted_average(records, "average_metric", "units"),
        "metric_low_count": sum_numbers(records, "metric_low_count"),
        "metric_mid_count": sum_numbers(records, "metric_mid_count"),
        "metric_high_count": sum_numbers(records, "metric_high_count"),
        "trained_rate": weighted_average(records, "trained_rate", "units"),
        "healthy_size_rate": weighted_average(records, "healthy_size_rate", "units"),
        "membership_growth_unit_rate": weighted_average(records, "membership_growth_unit_rate", "units"),
        "advancement_rate": weighted_average(records, "advancement_rate", "units"),
        "outdoor_rate": weighted_average(records, "outdoor_rate", "units"),
        "retention_rate": weighted_average(records, "retention_rate", "units"),
        "youth_current": current,
        "youth_prior": prior,
        "youth_delta": delta,
        "youth_growth_rate": ratio(delta, prior),
    }


def build_payload(source: Path) -> dict[str, Any]:
    reader = XlsxReader(source)
    try:
        councils, selected_name = extract_councils(reader, "Councils")
        pack_troops, _ = extract_councils(reader, "Pack_Troops")
        programs = {
            "All Units": ("Unit Metric - All", "All Units"),
            "Packs": ("Unit Metric - Packs", "Packs"),
            "Troops": ("Unit Metric - Troop", "Troops"),
            "Crews": ("Unit Metric - Crews", "Crews"),
            "Posts": ("Unit Metric - Posts", "Posts"),
            "Ships": ("Unit Metric - Ships", "Ships"),
        }
        unit_metrics = {
            label: extract_unit_metrics(reader, sheet_name, program)
            for label, (sheet_name, program) in programs.items()
        }
        pin_records = extract_pin(reader)
    finally:
        reader.close()

    if not councils:
        raise RuntimeError("No council ranking rows were found in the workbook")
    selected_name = selected_name or "Capitol Area Council 564"
    selected = next((record for record in councils if record["council"] == selected_name), councils[0])
    selected_name = selected["council"]

    pack_by_council = {record["council"]: record for record in pack_troops}
    pin_by_council = {record["council"]: record for record in pin_records}
    metrics_by_program = {
        program: {record["council"]: record for record in records}
        for program, records in unit_metrics.items()
    }

    for record in councils:
        record["pack_troop"] = pack_by_council.get(record["council"])
        record["pin"] = pin_by_council.get(record["council"])

    peers = [
        record
        for record in councils
        if record["council"] != selected_name
        and 0.8 <= float(record["units"]) / float(selected["units"]) <= 1.2
        and 0.8 <= float(record["current_youth"]) / float(selected["current_youth"]) <= 1.2
    ]
    peers.sort(key=lambda record: (-record["yoy_pct"], record["council"]))

    national_current = sum_numbers(councils, "current_youth")
    national_prior = sum_numbers(councils, "prior_youth")
    national_year_end = sum_numbers(councils, "year_end_youth")
    national_delta = national_current - national_prior
    national_ye_delta = national_current - national_year_end
    source_stat = source.stat()
    downloaded = datetime.fromtimestamp(source_stat.st_birthtime, CHICAGO)
    generated = datetime.now(CHICAGO)

    selected_metrics = {
        program: by_council.get(selected_name)
        for program, by_council in metrics_by_program.items()
    }
    selected_payload = dict(selected)
    selected_payload["unit_metrics"] = selected_metrics
    selected_payload["peer_count"] = len(peers)

    return {
        "metadata": {
            "title": "Council Performance Rankings",
            "source_name": source.name,
            "source_downloaded_at": downloaded.isoformat(),
            "generated_at": generated.isoformat(),
            "selected_council": selected_name,
            "methodology_version": "1.0",
            "privacy": "Council-level aggregates only; unit-level workbook rows are not published.",
        },
        "national": {
            "council_count": len(councils),
            "units": sum_numbers(councils, "units"),
            "current_youth": national_current,
            "prior_youth": national_prior,
            "yoy_delta": national_delta,
            "yoy_pct": ratio(national_delta, national_prior),
            "year_end_youth": national_year_end,
            "year_end_delta": national_ye_delta,
            "year_end_pct": ratio(national_ye_delta, national_year_end),
            "positive_growth_councils": sum(1 for record in councils if (record.get("yoy_pct") or 0) > 0),
        },
        "selected": selected_payload,
        "peers": peers,
        "councils": councils,
        "program_summaries": {
            program: summarize_program(program, records)
            for program, records in unit_metrics.items()
        },
        "unit_metrics": unit_metrics,
        "top_growth": sorted(councils, key=lambda record: (-record["yoy_pct"], record["council"]))[:10],
        "largest_councils": sorted(councils, key=lambda record: (-record["current_youth"], record["council"]))[:10],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("Councils Ranked.xlsx"),
        help="Source .xlsx workbook",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "latest.json",
        help="Output JSON path",
    )
    args = parser.parse_args()
    if not args.source.is_file():
        raise SystemExit(f"Source workbook not found: {args.source}")
    payload = build_payload(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "councils": len(payload["councils"]),
                "selected": payload["selected"]["council"],
                "peers": len(payload["peers"]),
                "source": payload["metadata"]["source_name"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
