#!/usr/bin/env python3
"""Validate the static site and its generated council-ranking payload."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    "index.html",
    "rankings.html",
    "unit-health.html",
    "about.html",
    "assets/dashboard.css",
    "assets/dashboard.js",
    "assets/topo-panel.png",
    "data/latest.json",
    ".nojekyll",
]


def main() -> int:
    failures: list[str] = []
    for relative in REQUIRED:
        if not (ROOT / relative).is_file():
            failures.append(f"Missing required file: {relative}")

    data = json.loads((ROOT / "data/latest.json").read_text(encoding="utf-8"))
    councils = data["councils"]
    selected = data["selected"]
    if not 200 <= len(councils) <= 300:
        failures.append(f"Unexpected council count: {len(councils)}")
    if selected["council"] != data["metadata"]["selected_council"]:
        failures.append("Selected council metadata does not match selected record")
    if selected["council"] == "Capitol Area Council 564" and len(data["peers"]) != 12:
        failures.append(f"Expected 12 corrected Capitol Area peers, found {len(data['peers'])}")

    expected_rank = {
        record["council"]: index
        for index, record in enumerate(
            sorted(councils, key=lambda item: (-item["yoy_pct"], item["council"])), 1
        )
    }
    for record in councils:
        if record["yoy_rank"] != expected_rank[record["council"]]:
            failures.append(f"YOY rank mismatch: {record['council']}")
            break
        recalculated = record["yoy_delta"] / record["prior_youth"] if record["prior_youth"] else None
        if recalculated is not None and abs(recalculated - record["yoy_pct"]) > 1e-12:
            failures.append(f"YOY percentage mismatch: {record['council']}")
            break

    html_text = "\n".join((ROOT / name).read_text(encoding="utf-8") for name in REQUIRED if name.endswith(".html"))
    if "/Users/" in html_text or "file://" in html_text:
        failures.append("Published HTML contains a local filesystem path")
    for name in ["index.html", "rankings.html", "unit-health.html", "about.html"]:
        text = (ROOT / name).read_text(encoding="utf-8")
        if text.count("<main") != 1 or text.count("</main>") != 1:
            failures.append(f"Malformed main structure: {name}")
        if not re.search(r'<meta name="viewport"', text):
            failures.append(f"Missing viewport metadata: {name}")

    result = {
        "status": "pass" if not failures else "fail",
        "councils": len(councils),
        "selected": selected["council"],
        "peers": len(data["peers"]),
        "failures": failures,
    }
    print(json.dumps(result, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
