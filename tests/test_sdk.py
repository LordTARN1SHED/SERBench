from __future__ import annotations

import gzip
from copy import deepcopy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from serbench import (  # noqa: E402
    PrivateLabelsError,
    ScoringError,
    ValidationError,
    load_dataset,
    load_labels,
    score_predictions,
    validate_predictions,
)
from serbench._reference_scorer import score_rows as reference_score_rows  # noqa: E402
from serbench.data import read_jsonl  # noqa: E402
from serbench.scoring import write_score_outputs  # noqa: E402


class SdkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.temp.name)
        (self.data_root / "example").mkdir()
        (self.data_root / "test500").mkdir()
        self.items = [
            {
                "state_id": "s1",
                "instance_id": "i1",
                "repo": "demo",
                "issue": "fix parser crash",
                "information_need": "where is parser input checked",
                "current_observation": "trace reaches parser",
                "current_hypothesis": "missing guard",
                "current_subgoal": "locate guard",
                "opened_files": ["src/parser.py"],
                "search_queries": ["parser guard"],
                "observed_evidence_ids": ["obs-1"],
                "candidate_evidence": [
                    {
                        "evidence_id": "obs-1",
                        "content_excerpt": "already seen",
                        "source_path": "src/parser.py",
                        "line_start": 1,
                        "line_end": 1,
                    },
                    {
                        "evidence_id": "e-1",
                        "content_excerpt": "parser validates input before parse",
                        "source_path": "src/parser.py",
                        "line_start": 10,
                        "line_end": 12,
                    },
                    {
                        "evidence_id": "e-2",
                        "content_excerpt": "parser returns a syntax error",
                        "source_path": "src/parser.py",
                        "line_start": 20,
                        "line_end": 22,
                    },
                    {
                        "evidence_id": "e-3",
                        "content_excerpt": "test expects a stable error",
                        "source_path": "tests/test_parser.py",
                        "line_start": 4,
                        "line_end": 8,
                    },
                    {
                        "evidence_id": "e-4",
                        "content_excerpt": "unrelated network code",
                        "source_path": "src/net.py",
                        "line_start": 1,
                        "line_end": 2,
                    },
                ],
            },
            {
                "state_id": "s2",
                "instance_id": "i2",
                "repo": "demo",
                "issue": "fix cache timeout",
                "information_need": "which branch handles timeout",
                "current_observation": "cache retries",
                "current_hypothesis": "timeout branch is stale",
                "current_subgoal": "find timeout branch",
                "opened_files": ["src/cache.py"],
                "search_queries": ["cache timeout"],
                "observed_evidence_ids": [],
                "candidate_evidence": [
                    {
                        "evidence_id": "shared",
                        "content_excerpt": "cache timeout branch",
                        "source_path": "src/cache.py",
                        "line_start": 10,
                        "line_end": 12,
                    },
                    {
                        "evidence_id": "e-5",
                        "content_excerpt": "cache retry policy",
                        "source_path": "src/cache.py",
                        "line_start": 20,
                        "line_end": 22,
                    },
                ],
            },
        ]
        self.labels = [
            {
                "state_id": "s1",
                "required_evidence_groups": [
                    {
                        "group_id": "bug",
                        "role": "bug_location",
                        "acceptable_evidence_ids": ["e-1", "e-2"],
                        "minimum_required": 1,
                        "necessity_weight": 2.0,
                    },
                    {
                        "group_id": "check",
                        "role": "verification_constraint",
                        "acceptable_evidence_ids": ["e-3"],
                        "minimum_required": 1,
                        "necessity_weight": 1.0,
                    },
                ],
                "alternative_minimal_sets": [["e-1", "e-3"], ["e-2", "e-3"]],
                "observed_evidence_ids": ["obs-1"],
            },
            {
                "state_id": "s2",
                "required_evidence_groups": [
                    {
                        "role": "bug_location",
                        "acceptable_evidence_ids": ["shared", "e-5"],
                        "minimum_required": 1,
                        "necessity_weight": 1.0,
                    }
                ],
                "alternative_minimal_sets": [["shared"]],
                "observed_evidence_ids": [],
            },
        ]
        self._write_jsonl(self.data_root / "example" / "items.jsonl", self.items)
        self._write_jsonl(self.data_root / "example" / "labels.jsonl", self.labels)
        with gzip.open(self.data_root / "test500" / "items.jsonl.gz", "wt", encoding="utf-8") as handle:
            for row in self.items:
                handle.write(json.dumps(row) + "\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    @staticmethod
    def _write_jsonl(path: Path, rows: list[dict]) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def _predictions(self) -> list[dict]:
        return [
            {
                "state_id": "s1",
                "method": "unit",
                "ranked_evidence_ids": ["e-4", "e-1", "e-3", "e-2"],
            },
            {
                "state_id": "s2",
                "method": "unit",
                "ranked_evidence_ids": ["e-5", "shared"],
            },
        ]

    def test_load_dataset_is_separate_from_labels_and_reads_gzip(self) -> None:
        dataset = load_dataset("example", self.data_root)
        self.assertEqual(len(dataset), 2)
        self.assertEqual(dataset[0]["state_id"], "s1")
        self.assertNotIn("required_evidence_groups", dataset[0])
        compressed = load_dataset("test500", self.data_root)
        self.assertEqual(len(compressed), 2)
        self.assertEqual(load_labels("example", self.data_root)[0]["state_id"], "s1")
        with self.assertRaises(PrivateLabelsError):
            load_labels("test500", self.data_root)

    def test_validation_rejects_missing_duplicate_unknown_and_observed(self) -> None:
        dataset = load_dataset("example", self.data_root)
        valid = self._predictions()
        report = validate_predictions(valid, dataset)
        self.assertEqual(report["per_method"], {"unit": 2})
        for bad in (
            valid[:1],
            valid + [dict(valid[0])],
            [dict(valid[0], ranked_evidence_ids=["unknown"]) , valid[1]],
            [dict(valid[0], ranked_evidence_ids=["e-1", "e-1"]), valid[1]],
        ):
            with self.assertRaises(ValidationError):
                validate_predictions(bad, dataset)
        observed = validate_predictions(
            [dict(valid[0], ranked_evidence_ids=["obs-1"]), valid[1]],
            dataset,
        )
        self.assertTrue(observed["valid"])

    def test_reference_scores_match_wrapper_and_prefix_metrics(self) -> None:
        dataset = load_dataset("example", self.data_root)
        predictions = self._predictions()
        labels = load_labels("example", self.data_root)
        expected = reference_score_rows(predictions, labels, (5, 8))
        actual = score_predictions(predictions, labels, (5, 8), dataset=dataset)
        self.assertEqual(actual, expected)
        self.assertEqual(actual[1]["unit"]["mss_complete@5"], 1.0)
        self.assertEqual(actual[1]["unit"]["mss_complete@8"], 1.0)

    def test_outputs_refuse_overwrite(self) -> None:
        directory = self.data_root / "scores"
        write_score_outputs([], {}, directory)
        with self.assertRaises(ScoringError):
            write_score_outputs([], {}, directory)

    def test_split_directory_cannot_masquerade_as_another_split(self) -> None:
        with self.assertRaises(Exception):
            load_dataset('test500', self.data_root / 'example')
        with self.assertRaises(PrivateLabelsError):
            load_labels('test500', self.data_root / 'example')

    def test_cached_rows_are_isolated(self) -> None:
        first = load_dataset('example', self.data_root)
        first[0]['candidate_evidence'][0]['evidence_id'] = 'corrupted'
        fresh = load_dataset('example', self.data_root)
        self.assertEqual(fresh[0]['candidate_evidence'][0]['evidence_id'], 'obs-1')

    def test_residual_gold_validation(self) -> None:
        for inconsistent in (True, False):
            labels = deepcopy(self.labels)
            labels[0]['required_evidence_groups'][0]['acceptable_evidence_ids'] = ['obs-1']
            if inconsistent:
                labels[0]['observed_evidence_ids'] = []
            with self.assertRaises(ValidationError):
                score_predictions(self._predictions(), labels, dataset=self.items)

    def test_observed_slots_and_group_thresholds(self) -> None:
        labels = deepcopy(self.labels)
        labels[0]['required_evidence_groups'][0]['minimum_required'] = 2
        labels[0]['alternative_minimal_sets'] = []
        predictions = self._predictions()
        predictions[0]['ranked_evidence_ids'] = ['obs-1', 'e-1', 'e-2', 'e-3']
        per_state, _ = score_predictions(predictions, labels, (2,3,4), dataset=self.items)
        row = per_state[0]
        self.assertEqual(row['mss_complete@3'], 0.0)
        self.assertEqual(row['mss_complete@4'], 1.0)
        self.assertEqual(row['group_recall@2'], 0.0)

    def test_baseline_does_not_mask_observed(self) -> None:
        from serbench.baseline import rank_row
        self.assertIn('obs-1', rank_row(self.items[0], 10))

    def test_cli_sample_commands_and_private_test_refusal(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "src")
        output = self.data_root / "predictions.jsonl"
        inspect = subprocess.run(
            [sys.executable, "-m", "serbench", "inspect", "--split", "example", "--data-dir", str(self.data_root)],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(inspect.returncode, 0, inspect.stderr)
        self.assertIn('"items": 2', inspect.stdout)
        baseline = subprocess.run(
            [sys.executable, "-m", "serbench", "baseline", "--split", "example", "--data-dir", str(self.data_root), "--output", str(output), "--k", "3"],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(baseline.returncode, 0, baseline.stderr)
        self.assertEqual(len(read_jsonl(output)), 2)
        validate = subprocess.run(
            [sys.executable, "-m", "serbench", "validate", "--split", "example", "--data-dir", str(self.data_root), "--predictions", str(output)],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(validate.returncode, 0, validate.stderr)
        score_dir = self.data_root / "score"
        score_proc = subprocess.run(
            [sys.executable, "-m", "serbench", "score", "--split", "example", "--data-dir", str(self.data_root), "--predictions", str(output), "--k", "5", "8", "--output", str(score_dir)],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(score_proc.returncode, 0, score_proc.stderr)
        self.assertTrue((score_dir / "summary.json").exists())
        private_score = subprocess.run(
            [sys.executable, "-m", "serbench", "score", "--split", "test500", "--data-dir", str(self.data_root), "--predictions", str(output), "--output", str(self.data_root / "private")],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(private_score.returncode, 0)
        self.assertIn("private", private_score.stderr.lower())


if __name__ == "__main__":
    unittest.main()
