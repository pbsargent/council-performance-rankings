"""Regression tests for publication gates; no network, credentials, or source units needed."""

import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from build_site import count_coming_units
from check_data_quality import reconcile_units
from prepare_refresh import check_freshness, check_retention_continuity, prepare
from source_contract import COUNCIL_HEADERS, METRIC_HEADERS, PROGRAM_SHEETS, inspect_source
from validate_site import ROOT, competition_ranks, validate
from verify_release import verify_files


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "data/latest.json").read_text())

    def test_current_payload_and_brand_pass(self):
        self.assertEqual(validate(self.data), [])

    def test_zero_unit_program_can_lose_continuation_metric(self):
        previous = {"unit_metrics": {"Posts": [{"council_number": "802", "retention_rate": 1.5, "units": 1}]}}
        row = {"council_number": "802", "council": "Transatlantic Council, BSA 802", "units": 0, "retention_rate": None}
        payload = {"unit_metrics": {"Posts": [row]}}
        original = copy.deepcopy(payload)
        self.assertEqual(check_retention_continuity(previous, payload), [
            {"program": "Posts", "council": row["council"], "council_number": "802", "units": 0}])
        self.assertEqual(payload, original)
        for units in (1, 2, None):
            with self.subTest(units=units):
                row["units"] = units
                with self.assertRaisesRegex(ValueError, "Previously populated retention"):
                    check_retention_continuity(previous, payload)

    def test_zero_and_above_100_metric_values_are_preserved(self):
        previous = {"unit_metrics": {"Posts": [{"council_number": "802", "retention_rate": 1.5}]}}
        for units in (0, 1):
            for rate in (0, 1.5, 5):
                with self.subTest(units=units, rate=rate):
                    payload = {"unit_metrics": {"Posts": [{"council_number": "802", "units": units, "retention_rate": rate}]}}
                    original = copy.deepcopy(payload)
                    self.assertEqual(check_retention_continuity(previous, payload), [])
                    self.assertEqual(payload, original)

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
                self.sheets = dict.fromkeys({"Councils", "Pack_Troops", "Unit_PIN", "Data_Census_Gov", "Units", *PROGRAM_SHEETS.values()})

            def close(self):
                pass

            def rows(self, sheet):
                if sheet == "Units":
                    yield 1, {1: "Council", 2: "Unit", 5: "Unit_ID", 6: "Coming"}
                    for index, name in enumerate(names, 2):
                        yield index, {1: name, 2: "Pack", 5: index, 6: "Yes" if index == 2 else None}
                elif sheet in PROGRAM_SHEETS.values():
                    yield 1, METRIC_HEADERS
                    for index, name in enumerate(names, 2):
                        yield index, {2: name, 3: 1, 19: 1.5}
                elif sheet == "Unit_PIN":
                    yield 1, {2: "Council", 3: "Units", 4: "pinstatus", 5: "applystatus", 6: "strisfundraisingstatusactive", 7: "stristrialvisitallowed", 8: "unitfee", 9: "strupdatedinayear", 10: "meetingday"}
                    for index, name in enumerate(names, 2):
                        yield index, {2: name, 3: 1}
                else:
                    yield 2, {**COUNCIL_HEADERS, 15: "TAY", 16: "TAY %", 17: "TAY Rank", 18: "Sqare Miles", 19: "% Urban"}
                    for index, name in enumerate(names, 3):
                        yield index, {2: name, 3: 1, 4: 10, 5: 9, 9: 9, 15: 1000, 18: 1234.5, 19: 0.75}

        payload = {"councils": [{"council": name, "units": 1, "coming_units": int(name == names[0]), "current_youth": 10, "prior_youth": 9, "year_end_youth": 9, "tay": 1000, "square_miles": 1234.5, "urban_pct": 0.75} for name in names],
                   "unit_metrics": {program: [{"council": name, "retention_rate": 1.5} for name in names] for program in PROGRAM_SHEETS}}
        with patch("source_contract.XlsxReader", Reader):
            result = inspect_source(Path("Councils Ranked.xlsx"), payload)
            self.assertEqual(result["retention_above_100_count"], 1200)
            self.assertEqual(result["coming_units"], 1)
            altered = copy.deepcopy(payload)
            altered["councils"][0]["coming_units"] = 0
            with self.assertRaisesRegex(ValueError, "Coming unit count mismatch"):
                inspect_source(Path("Councils Ranked.xlsx"), altered)
            for field in ("square_miles", "urban_pct"):
                altered = copy.deepcopy(payload)
                altered["councils"][0][field] = 0
                with self.assertRaisesRegex(ValueError, "Source mismatch"):
                    inspect_source(Path("Councils Ranked.xlsx"), altered)
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

    def test_coming_units_fail_closed_on_unknown_flags_duplicates_or_short_rosters(self):
        class Reader:
            sheets = {"Units": None}

            def rows(self, sheet):
                yield 1, {1: "Council", 2: "Unit", 5: "Unit_ID", 6: "Coming"}
                yield 2, {1: "Council A", 2: "Pack", 5: 1, 6: "Yes"}
                yield 3, {1: "Council A", 2: "Pack", 5: unit_id, 6: flag}

        for unit_id, flag, total, error in [
            (2, "?", 2, "Unrecognized Coming flag"),
            (1, None, 2, "duplicate Unit_ID"),
            (2, None, 3, "does not reconcile"),
        ]:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                count_coming_units(Reader(), {"Council A": total})

    def test_unit_reconciliation_counts_overlap_once_and_reports_offsetting_gaps(self):
        class Reader:
            sheets = {"Units": None}

            def rows(self, sheet):
                yield 1, {1: "Council", 2: "Unit", 5: "Unit_ID", 6: "Coming"}
                yield 2, {1: "Council A", 2: "CLUB", 5: 1, 6: "Yes"}
                yield 3, {1: "Council A", 2: "Pack", 5: 2}
                yield 4, {1: "Council B", 2: "Club", 5: 3}
                yield 5, {1: "Council B", 2: "Troop", 5: 4, 6: "Yes"}

        data = {
            "councils": [{"council": "Council A", "units": 2}, {"council": "Council B", "units": 2}],
            "unit_metrics": {"All Units": [{"council": "Council A", "units": 0}, {"council": "Council B", "units": 1}]},
        }
        report = reconcile_units(data, Reader())
        self.assertEqual((report["clubs"], report["coming_units"], report["coming_clubs"]), (2, 2, 1))
        self.assertEqual(report["remaining_gap"], 0)
        self.assertEqual(report["councils_with_gap"], 2)
        self.assertEqual([row["remaining_gap"] for row in report["council_gaps"]], [1, -1])


if __name__ == "__main__":
    unittest.main()
