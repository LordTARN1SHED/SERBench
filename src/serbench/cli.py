"""Command-line interface for inspecting, retrieving, validating, and scoring SERBench."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .baseline import generate_predictions
from .data import DataError, PrivateLabelsError, SPLITS, load_dataset, load_labels, read_jsonl
from .scoring import (
    ScoringError,
    ValidationError,
    score_predictions,
    validate_labels,
    validate_predictions,
    write_score_outputs,
)


def _common_split(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--split",
        choices=SPLITS,
        required=True,
        help="benchmark split to use",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="override the data root (otherwise SERBENCH_DATA_DIR or a local data/ is used)",
    )


def _write_jsonl(
    rows: Sequence[dict[str, Any]],
    path: Path,
    *,
    overwrite: bool,
) -> None:
    if path.exists() and not overwrite:
        raise ScoringError(
            f"refusing to overwrite existing output {path}; pass --overwrite to replace it"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _cmd_inspect(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.split, args.data_dir)
    candidate_count = 0
    state_ids: list[str] = []
    fields: set[str] = set()
    for row in dataset:
        fields.update(str(key) for key in row)
        state_ids.append(str(row.get("state_id", "")))
        candidates = row.get("candidate_evidence", [])
        if isinstance(candidates, list):
            candidate_count += len(candidates)
    result = {
        "split": args.split,
        "items": len(dataset),
        "states": len(set(state_ids)),
        "candidate_evidence": candidate_count,
        "item_fields": sorted(fields),
        "path": str(dataset.path) if dataset.path else None,
        "labels_loaded": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _cmd_baseline(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.split, args.data_dir)
    predictions = generate_predictions(dataset, k=args.k)
    _write_jsonl(predictions, args.output, overwrite=args.overwrite)
    print(
        json.dumps(
            {
                "split": args.split,
                "method": "bm25_starter",
                "states": len(predictions),
                "output": str(args.output),
                "k": args.k,
            },
            sort_keys=True,
        )
    )
    return 0


def _read_optional_labels(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.labels is not None:
        try:
            return read_jsonl(args.labels)
        except DataError as exc:
            raise ValidationError(f"could not read labels file {args.labels}: {exc}") from exc
    if args.split == "test500":
        raise PrivateLabelsError(
            "Test500 labels are private; local score requires an organizer-supplied "
            "path via --labels"
        )
    # Keep the private-label error explicit for public Test500 users.
    return load_labels(args.split, args.data_dir)


def _cmd_validate(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.split, args.data_dir)
    try:
        predictions = read_jsonl(args.predictions)
    except DataError as exc:
        raise ValidationError(
            f"could not read predictions file {args.predictions}: {exc}"
        ) from exc
    report = validate_predictions(
        predictions,
        dataset,
        strict=not args.allow_subset,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _cmd_score(args: argparse.Namespace) -> int:
    dataset = load_dataset(args.split, args.data_dir)
    try:
        predictions = read_jsonl(args.predictions)
    except DataError as exc:
        raise ValidationError(
            f"could not read predictions file {args.predictions}: {exc}"
        ) from exc
    labels = _read_optional_labels(args)
    per_state, summary = score_predictions(
        predictions,
        labels,
        args.k,
        dataset=dataset,
        strict=not args.allow_subset,
    )
    write_score_outputs(
        per_state,
        summary,
        args.output,
        overwrite=args.overwrite,
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serbench",
        description=(
            "Dependency-free SDK tools for the public SERBench benchmark. "
            "The BM25 command is a new starter baseline, not a paper reproduction."
        ),
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect = subparsers.add_parser(
        "inspect", help="show item counts and schema fields without loading labels"
    )
    _common_split(inspect)
    inspect.set_defaults(handler=_cmd_inspect)

    baseline = subparsers.add_parser(
        "baseline",
        help="write predictions from the dependency-free BM25 starter baseline",
    )
    _common_split(baseline)
    baseline.add_argument("--output", type=Path, required=True, help="prediction JSONL path")
    baseline.add_argument("--k", type=int, default=8, help="maximum ranked IDs per state")
    baseline.add_argument(
        "--overwrite",
        action="store_true",
        help="replace an existing prediction output",
    )
    baseline.set_defaults(handler=_cmd_baseline)

    validate = subparsers.add_parser(
        "validate",
        help="validate strict prediction coverage, candidate IDs, and observed slots",
    )
    _common_split(validate)
    validate.add_argument(
        "--predictions", type=Path, required=True, help="prediction JSONL path"
    )
    validate.add_argument(
        "--allow-subset",
        action="store_true",
        help="allow incomplete per-method coverage for local analysis",
    )
    validate.set_defaults(handler=_cmd_validate)

    score = subparsers.add_parser(
        "score",
        help="score validated predictions and write per-state and summary JSON",
    )
    _common_split(score)
    score.add_argument(
        "--predictions", type=Path, required=True, help="prediction JSONL path"
    )
    score.add_argument(
        "--labels",
        type=Path,
        default=None,
        help=(
            "organizer/custom labels JSONL(.gz); omit for bundled public labels "
            "(Test500 labels are not public)"
        ),
    )
    score.add_argument(
        "--k",
        type=int,
        nargs="+",
        default=[5, 8],
        help="one or more ranking cutoffs (default: 5 8)",
    )
    score.add_argument("--output", type=Path, required=True, help="score output directory")
    score.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing per_state_scores.jsonl/summary.json",
    )
    score.add_argument(
        "--allow-subset",
        action="store_true",
        help="allow incomplete per-method coverage for local analysis",
    )
    score.set_defaults(handler=_cmd_score)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (DataError, ScoringError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


__all__ = ["build_parser", "main"]
