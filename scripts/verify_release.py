#!/usr/bin/env python3
"""Wait for this commit's Pages success and verify cache-busted live files exactly."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from validate_site import ROOT, PAGES, validate

SITE = "https://pbsargent.github.io/council-performance-rankings/"
REPO = "pbsargent/council-performance-rankings"
ASSETS = [*PAGES, "assets/dashboard.css", "assets/dashboard.js", "assets/scouting-america-signature.png", "data/latest.json"]


def git_file(commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=ROOT)


def verify_files(expected, fetch):
    for path, content in expected.items():
        if fetch(path) != content:
            raise ValueError(f"Live file does not match pushed commit: {path}")
    payload = json.loads(expected["data/latest.json"])
    failures = validate(payload)
    if failures:
        raise ValueError("; ".join(failures))
    retention = [r["retention_rate"] for rows in payload["unit_metrics"].values() for r in rows if r["retention_rate"] is not None]
    return {"councils": len(payload["councils"]), "generated_at": payload["metadata"]["generated_at"],
            "source_downloaded_at": payload["metadata"]["source_downloaded_at"],
            "maximum_retention": max(retention) if retention else None,
            "retention_above_100_count": sum(v > 1 for v in retention),
            "tay_covered_councils": payload["national"]["tay_covered_councils"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--expected", type=Path, required=True, help="Candidate retained in private run directory")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--token-file", type=Path, default=Path("/Users/petersargent/.config/other-council-dashboard/github-token"))
    args = parser.parse_args()
    report = {"status": "fail", "stage": "deployment", "live_url": SITE}
    try:
        commit = subprocess.check_output(["git", "rev-parse", args.commit], cwd=ROOT, text=True).strip()
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Expected a full commit SHA")
        report["commit"] = commit
        expected = {path: git_file(commit, path) for path in ASSETS}
        if expected["data/latest.json"] != args.expected.read_bytes():
            raise ValueError("Pushed payload does not match validated candidate")
        environment = dict(os.environ, GH_TOKEN=args.token_file.read_text().strip())
        deadline = time.monotonic() + args.timeout
        while True:
            # Token stays in the child environment, never in logs or command arguments.
            result = subprocess.run(["gh", "api", f"repos/{REPO}/actions/runs?head_sha={commit}&per_page=100"], env=environment, capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError("Could not query GitHub deployment status")
            runs = [r for r in json.loads(result.stdout)["workflow_runs"] if r["head_sha"] == commit and r["name"] == "pages build and deployment"]
            if runs:
                run = max(runs, key=lambda r: r["id"])
                report.update(pages_url=run["html_url"], pages_result=run.get("conclusion"))
                if run["status"] == "completed":
                    if run["conclusion"] != "success":
                        raise ValueError(f"Pages deployment failed: {run['conclusion']}")
                    break
            if time.monotonic() >= deadline:
                raise TimeoutError("Pages deployment did not complete within the timeout")
            print("Waiting for Pages deployment of " + commit[:7], flush=True)
            time.sleep(10)
        report["stage"] = "live verification"
        cache_bust = f"{commit}-{time.time_ns()}"

        def fetch(path):
            request = Request(SITE + path + "?cb=" + cache_bust, headers={"Cache-Control": "no-cache"})
            with urlopen(request, timeout=30) as response:
                if response.status != 200 or not response.url.startswith(SITE):
                    raise ValueError(f"Unexpected HTTP response for {path}")
                return response.read()

        report.update(verify_files(expected, fetch), status="pass", stage="live verified",
                      verified_at=datetime.now(timezone.utc).isoformat(),
                      payload_sha256=hashlib.sha256(expected["data/latest.json"]).hexdigest())
    except Exception as error:
        report["error"] = str(error)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return int(report["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
