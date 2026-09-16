"""Minimal custom retriever example.

Run from an editable checkout, for example::

    python examples/custom_method.py --split example --output predictions.jsonl

The example only sees item rows and candidate evidence.  It never loads or
hardcodes labels; replace ``rank_item`` with a model or search service in a
real method.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

try:  # Make the example convenient before a local editable install.
    from serbench import load_dataset
except ModuleNotFoundError:  # pragma: no cover - subprocess convenience path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from serbench import load_dataset


def rank_item(row: Mapping[str, Any], k: int) -> list[str]:
    """Return a deterministic source-path order for one item."""

    candidates = [
        candidate
        for candidate in row.get("candidate_evidence", [])
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("evidence_id"), str)
    ]
    candidates.sort(
        key=lambda candidate: (
            str(candidate.get("source_path", "")),
            int(candidate.get("line_start", 0) or 0),
            str(candidate["evidence_id"]),
        )
    )
    return [str(candidate["evidence_id"]) for candidate in candidates[:k]]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("example", "cal500", "test500"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--k", type=int, default=8)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    if args.k <= 0:
        parser.error("--k must be positive")
    if args.output.exists() and not args.overwrite:
        parser.error(f"refusing to overwrite {args.output}; pass --overwrite")
    dataset = load_dataset(args.split, args.data_dir)
    rows = [
        {
            "state_id": row["state_id"],
            "method": "custom_source_order",
            "ranked_evidence_ids": rank_item(row, args.k),
        }
        for row in dataset
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    print(json.dumps({"split": args.split, "states": len(rows), "output": str(args.output)}))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
