"""Regression tests for publication gates; no network, credentials, or source units needed."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from prepare_refresh import check_freshness, prepare
from source_contract import COUNCIL_HEADERS, METRIC_HEADERS, PROGRAM_SHEETS, inspect_source
from validate_site import ROOT, competition_ranks, validate
from verify_release import verify_files


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/latest.json").read_text())

    def test_current_payload_and_brand_pass(self):
        self.assertEqual(validate(self.data), [])

    def test_competition_ties_and_blank_ranks(self):
        rows = [{"council": name, "rate": value} for name, value in [("A", .1), ("B", .1), ("C", .05), ("D", None)]]
        self.assertEqual(competition_ranks(rows, "rate"), {"A": 1, "B": 1, "C": 3})

    def test_unit_row_injection_is_blocked(self):
        self.data["unit_metrics"]["All Units"][0]["unit_number"] = "123"
        self.assertTrue(any("schema" in f for f in validate(self.data)))

    def test_tay_removal_is_blocked(self):
        del self.data["councils"][0]["tay"]
        self.assertTrue(any("schema" in f for f in validate(self.data)))

    def test_incorrect_rank_is_blocked(self):
        self.data["councils"][0]["yoy_rank"] = 999
        self.assertTrue(any("yoy_rank" in f for f in validate(self.data)))

    def test_peer_count_is_derived_not_fixed(self):
        self.data["peers"].pop()
        self.assertTrue(any("Peer set" in f for f in validate(self.data)))

    def test_stale_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "Councils Ranked.xlsx"
            source.touch()
            with self.assertRaisesRegex(ValueError, "new download"):
                check_freshness(source, datetime.now(timezone.utc) + timedelta(seconds=2))

    def test_failed_prepare_preserves_working_payload_and_records_stage(self):
        before = (ROOT / "data/latest.json").read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            with patch("prepare_refresh.subprocess.check_output", side_effect=["main\n", "", "abc\nabc\n"]):
                report = prepare(Path(directory) / "missing.xlsx", datetime.now(timezone.utc), Path(directory) / "run")
            self.assertEqual(report["status"], "fail")
            self.assertEqual(report["stage"], "source acquisition")
            self.assertTrue((Path(directory) / "run/report.json").exists())
        self.assertEqual(before, (ROOT / "data/latest.json").read_bytes())

    def test_live_payload_mismatch_is_blocked(self):
        expected = {"data/latest.json": json.dumps(self.data).encode()}
        with self.assertRaisesRegex(ValueError, "does not match"):
            verify_files(expected, lambda path: b"stale")

    def test_source_schema_drift_and_retention_clamping_are_blocked(self):
        names = [f"Council {index:03d}" for index in range(200)]

        class Reader:
            def __init__(self, path):
                self.sheets = dict.fromkeys({"Councils", "Pack_Troops", "Unit_PIN", "Data_Census_Gov", *PROGRAM_SHEETS.values()})

            def close(self):
                pass

            def rows(self, sheet):
                if sheet in PROGRAM_SHEETS.values():
                    yield 1, METRIC_HEADERS
                    for index, name in enumerate(names, 2):
                        yield index, {2: name, 3: 1, 19: 1.5}
                elif sheet == "Unit_PIN":
                    yield 1, {2: "Council", 3: "Units", 4: "pinstatus", 5: "applystatus", 6: "strisfundraisingstatusactive", 7: "stristrialvisitallowed", 8: "unitfee", 9: "strupdatedinayear", 10: "meetingday"}
                    for index, name in enumerate(names, 2):
                        yield index, {2: name, 3: 1}
                else:
                    yield 2, {**COUNCIL_HEADERS, 15: "TAY", 16: "TAY %", 17: "TAY Rank"}
                    for index, name in enumerate(names, 3):
                        yield index, {2: name, 3: 1, 4: 10, 5: 9, 9: 9, 15: 1000}

        payload = {"councils": [{"council": name, "units": 1, "current_youth": 10, "prior_youth": 9, "year_end_youth": 9, "tay": 1000} for name in names],
                   "unit_metrics": {program: [{"council": name, "retention_rate": 1.5} for name in names] for program in PROGRAM_SHEETS}}
        with patch("source_contract.XlsxReader", Reader):
            result = inspect_source(Path("Councils Ranked.xlsx"), payload)
            self.assertEqual(result["retention_above_100_count"], 1200)
            clamped = copy.deepcopy(payload)
            clamped["unit_metrics"]["Ships"][0]["retention_rate"] = 1
            with self.assertRaisesRegex(ValueError, "retention was changed"):
                inspect_source(Path("Councils Ranked.xlsx"), clamped)
            class DriftReader(Reader):
                def rows(self, sheet):
                    for row, cells in super().rows(sheet):
                        if sheet == "Councils" and row == 2:
                            cells = {**cells, 15: "TAY moved to another column"}
                        yield row, cells
            with patch("source_contract.XlsxReader", DriftReader):
                with self.assertRaisesRegex(ValueError, "Schema drift"):
                    inspect_source(Path("Councils Ranked.xlsx"), payload)


if __name__ == "__main__":
    unittest.main()
