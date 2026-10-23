#!/usr/bin/env python3
"""Prepare a source-verified refresh; replace latest.json only after every gate passes."""

import argparse
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from build_site import build_payload
from source_contract import inspect_source
from validate_site import ROOT, validate


def check_freshness(source, started, now=None):
    if started.tzinfo is None:
        raise ValueError("Acquisition start must include a timezone")
    now = now or datetime.now(timezone.utc)
    stat = source.stat()
    acquired = datetime.fromtimestamp(getattr(stat, "st_birthtime", stat.st_mtime), timezone.utc)
    modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc)
    if not started <= acquired <= now or modified < started or modified > now:
        raise ValueError("Source is not a new download from this acquisition window; do not copy or touch an older workbook")
    if (now - started).total_seconds() > 3600:
        raise ValueError("Acquisition window exceeds one hour; start a new download attempt")
    return acquired


def prepare(source, started, run_dir, check_only=False):
    stage = "source acquisition"
    report = {"status": "fail", "stage": stage, "run_started_at": started.isoformat()}
    run_dir.mkdir(parents=True, exist_ok=False)
    lock = None
    try:
        if not check_only:
            stage = "repository preflight"
            lock = open(Path(tempfile.gettempdir()) / "council-rankings-refresh.lock", "a")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip()
            dirty = subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip()
            if branch != "main" or dirty:
                raise ValueError("Refresh requires main with clean tracked and staged files; preserve unrelated work and report the blocker")
            revisions = subprocess.check_output(["git", "rev-parse", "HEAD", "origin/main"], cwd=ROOT, text=True).splitlines()
            if len(revisions) != 2 or revisions[0] != revisions[1]:
                raise ValueError("Local main differs from origin/main; resolve the pending push or remote change before refreshing")
        stage = "source acquisition"
        acquired = check_freshness(source, started)
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        source_stats = inspect_source(source)
        report.update(source_stats, source_sha256=digest, source_downloaded_at=acquired.isoformat())
        stage = "build"
        snapshot = run_dir / "Councils Ranked.xlsx"
        shutil.copyfile(source, snapshot)
        payload = build_payload(snapshot, downloaded_at=acquired)
        if payload["metadata"]["source_sha256"] != digest:
            raise ValueError("Source changed during acquisition")
        candidate = run_dir / "latest.json"
        candidate.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        stage = "source reconciliation"
        inspect_source(snapshot, payload)
        stage = "site validation"
        failures = validate(payload)
        if failures:
            raise ValueError("; ".join(failures))
        stage = "data quality"
        quality = subprocess.run([sys.executable, str(ROOT / "scripts/check_data_quality.py"), "--input", str(candidate)], capture_output=True, text=True, timeout=60)
        (run_dir / "data-quality.json").write_text(quality.stdout, encoding="utf-8")
        if quality.returncode:
            raise ValueError(quality.stdout or quality.stderr)
        stage = "baseline reconciliation"
        baseline_bytes = (ROOT / "data/latest.json").read_bytes()
        previous = json.loads(baseline_bytes)
        old = {r["council_number"]: r for r in previous["councils"]}
        new = {r["council_number"]: r for r in payload["councils"]}
        for number in old.keys() & new.keys():
            if old[number].get("tay") not in (None, 0) and new[number].get("tay") in (None, 0):
                raise ValueError(f"Previously populated TAY is now missing: {new[number]['council']}")
        for program, records in payload["unit_metrics"].items():
            prior = {r["council_number"]: r for r in previous["unit_metrics"][program]}
            for row in records:
                before = prior.get(row["council_number"], {})
                if before.get("retention_rate") is not None and row["retention_rate"] is None:
                    raise ValueError(f"Previously populated retention is now missing: {program} {row['council']}")
        report.update(previous_councils=len(old), added_councils=sorted(new.keys()-old.keys()),
                      removed_councils=sorted(old.keys()-new.keys()),
                      generated_at=payload["metadata"]["generated_at"],
                      candidate_sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
                      baseline_sha256=hashlib.sha256(baseline_bytes).hexdigest(),
                      tay_missing_councils=[r["council"] for r in payload["councils"] if r.get("tay") in (None, 0)])
        stage = "promote candidate"
        if not check_only:
            if (ROOT / "data/latest.json").read_bytes() != baseline_bytes:
                raise ValueError("Working payload changed during preparation; another refresh may be running")
            descriptor, temporary = tempfile.mkstemp(prefix=".latest-", suffix=".json", dir=ROOT / "data")
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(candidate.read_bytes())
                os.replace(temporary, ROOT / "data/latest.json")
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        report.update(status="pass", stage="checked only" if check_only else "ready for diff review")
    except Exception as error:
        report.update(status="fail", stage=stage, error=str(error))
    finally:
        if lock:
            lock.close()
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Original new browser download, not a renamed copy")
    parser.add_argument("--acquisition-started-at", required=True, help="ISO timestamp captured before the download action")
    parser.add_argument("--run-dir", type=Path, required=True, help="New private run directory; must not already exist")
    parser.add_argument("--check-only", action="store_true", help="Validate without replacing working data/latest.json")
    args = parser.parse_args()
    report = prepare(args.source, datetime.fromisoformat(args.acquisition_started_at), args.run_dir, args.check_only)
    print(json.dumps(report, indent=2))
    return int(report["status"] != "pass")


if __name__ == "__main__":
    raise SystemExit(main())
