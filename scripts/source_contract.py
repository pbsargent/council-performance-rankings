"""Workbook identity, fixed-column schema, and source-to-payload checks (stdlib only)."""

import re
from pathlib import Path

from build_site import XlsxReader, clean_number

PROGRAM_SHEETS = {
    "All Units": "Unit Metric - All", "Packs": "Unit Metric - Packs",
    "Troops": "Unit Metric - Troop", "Crews": "Unit Metric - Crews",
    "Posts": "Unit Metric - Posts", "Ships": "Unit Metric - Ships",
}
COUNCIL_HEADERS = {2: "Council", 3: "Units", 4: "Current Youth", 5: "Youth Last Year", 9: "Youth YE'25"}
METRIC_HEADERS = {
    2: "Council", 4: "Average Metric", 6: "0-2", 7: 3, 8: "4-5",
    10: "0-2", 11: 3, 12: "4-5", 14: "UL & CC Trained",
    15: "Exceeds Small Unit Threshold", 16: "Membership YOY Growth",
    18: "Outdoor", 19: "Retention", 21: "Total Youth current", 22: "Total Youth Prev Yr",
}


def council_rows(reader, sheet, first_row):
    return [cells for row, cells in reader.rows(sheet) if row >= first_row
            and isinstance(cells.get(2), str) and re.search(r"\d{3}$", cells[2].strip())]


def inspect_source(source: Path, payload=None):
    """Fail on schema drift; compare every source council, TAY, and retention value."""
    if not re.fullmatch(r"Councils Ranked(?: \(\d+\))?\.xlsx", source.name):
        raise ValueError("Expected canonical Councils Ranked.xlsx (browser numeric suffix allowed)")
    reader = XlsxReader(source)
    try:
        required = {"Councils", "Pack_Troops", "Unit_PIN", "Data_Census_Gov", *PROGRAM_SHEETS.values()}
        missing = required - reader.sheets.keys()
        if missing:
            raise ValueError(f"Missing canonical worksheets: {sorted(missing)}")
        contracts = {
            "Councils": (2, {**COUNCIL_HEADERS, 15: "TAY", 16: "TAY %", 17: "TAY Rank"}),
            "Pack_Troops": (2, COUNCIL_HEADERS),
            "Unit_PIN": (1, {2: "Council", 3: "Units", 4: "pinstatus", 5: "applystatus",
                             6: "strisfundraisingstatusactive", 7: "stristrialvisitallowed",
                             8: "unitfee", 9: "strupdatedinayear", 10: "meetingday"}),
            **{sheet: (1, METRIC_HEADERS) for sheet in PROGRAM_SHEETS.values()},
        }
        for sheet, (row_number, expected) in contracts.items():
            header = next((cells for row, cells in reader.rows(sheet) if row == row_number), {})
            for col, value in expected.items():
                if header.get(col) != value:
                    raise ValueError(f"Schema drift: {sheet} row {row_number} column {col}: expected {value!r}, got {header.get(col)!r}")
        rows = council_rows(reader, "Councils", 3)
        source_names = [cells[2].strip() for cells in rows]
        if len(set(source_names)) != len(rows) or not 200 <= len(rows) <= 300:
            raise ValueError("Source council population is empty, duplicated, or outside 200–300")
        for sheet, first_row in (("Pack_Troops", 3), ("Unit_PIN", 2)):
            names = [c[2].strip() for c in council_rows(reader, sheet, first_row)]
            if set(names) != set(source_names) or len(names) != len(source_names):
                raise ValueError(f"Source population mismatch in {sheet}")
        for cells in rows:
            for col in (3, 4, 5, 9):
                if clean_number(cells.get(col)) is None:
                    raise ValueError(f"Missing numeric source value: {cells[2]} column {col}")
            if cells.get(15) not in (None, "") and clean_number(cells[15]) is None:
                raise ValueError(f"Invalid source TAY: {cells[2]}")
        if payload is not None:
            generated = {r["council"]: r for r in payload["councils"]}
            if set(source_names) != generated.keys() or len(rows) != len(payload["councils"]):
                raise ValueError("Source council population does not exactly match generated rows")
            for cells in rows:
                record = generated[cells[2].strip()]
                for field, col in {"units": 3, "current_youth": 4, "prior_youth": 5, "year_end_youth": 9, "tay": 15}.items():
                    if record.get(field) != clean_number(cells.get(col)):
                        raise ValueError(f"Source mismatch: {record['council']} {field}")
        retention = []
        for program, sheet in PROGRAM_SHEETS.items():
            metric_rows = council_rows(reader, sheet, 2)
            names = [cells[2].strip() for cells in metric_rows]
            if set(names) != set(source_names) or len(names) != len(source_names):
                raise ValueError(f"Source population mismatch in {sheet}")
            generated = {r["council"]: r for r in payload["unit_metrics"][program]} if payload else {}
            for cells in metric_rows:
                value = clean_number(cells.get(19))
                if value is not None:
                    retention.append(value)
                if payload is not None and generated[cells[2].strip()].get("retention_rate") != value:
                    raise ValueError(f"Source retention was changed: {sheet} {cells[2]}")
        return {"councils": len(rows), "worksheets": sorted(required),
                "maximum_retention": max(retention) if retention else None,
                "retention_above_100_count": sum(value > 1 for value in retention),
                "tay_covered_councils": sum(clean_number(c.get(15)) not in (None, 0) for c in rows)}
    finally:
        reader.close()
