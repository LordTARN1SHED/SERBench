#!/usr/bin/env python3
"""Reference SERBench grouped minimal-evidence scoring formulas.

This module is intentionally a standalone copy of the v5.6 release scorer.
The public wrapper in :mod:`serbench.scoring` performs input validation before
calling these functions; the formulas here remain unchanged.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from statistics import mean
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def group_completion_rank(
    ranked_ids: list[str], group: dict[str, Any], k: int
) -> int | None:
    acceptable = set(group["acceptable_evidence_ids"])
    required = int(group.get("minimum_required", 1))
    hits = 0
    seen = set()
    for rank, evidence_id in enumerate(ranked_ids[:k], start=1):
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        if evidence_id in acceptable:
            hits += 1
            if hits >= required:
                return rank
    return None


def ideal_group_dcg(groups: list[dict[str, Any]], weights: list[float], k: int) -> float:
    """Compute the exact certificate-aware ideal DCG for the small gold universe."""
    candidates = sorted(
        {
            str(evidence_id)
            for group in groups
            for evidence_id in group["acceptable_evidence_ids"]
        }
    )
    if not candidates or k <= 0:
        return 0.0
    if len(candidates) > 20:
        # A conservative bounded fallback for external certificates much larger
        # than SERBench, whose maximum gold universe is 14 evidence IDs.
        return sum(weights)

    evidence_index = {evidence_id: index for index, evidence_id in enumerate(candidates)}
    group_masks = []
    requirements = []
    for group in groups:
        mask = 0
        for evidence_id in group["acceptable_evidence_ids"]:
            mask |= 1 << evidence_index[str(evidence_id)]
        group_masks.append(mask)
        requirements.append(int(group.get("minimum_required", 1)))

    @lru_cache(maxsize=None)
    def completed(mask: int, group_index: int) -> bool:
        return bin(mask & group_masks[group_index]).count("1") >= requirements[group_index]

    current = {0: 0.0}
    best = 0.0
    for rank in range(1, min(k, len(candidates)) + 1):
        next_scores: dict[int, float] = {}
        discount = math.log2(rank + 1)
        for previous_mask, previous_score in current.items():
            for candidate_index in range(len(candidates)):
                bit = 1 << candidate_index
                if previous_mask & bit:
                    continue
                new_mask = previous_mask | bit
                gain = sum(
                    weight / discount
                    for group_index, weight in enumerate(weights)
                    if not completed(previous_mask, group_index)
                    and completed(new_mask, group_index)
                )
                score = previous_score + gain
                if score > next_scores.get(new_mask, -1.0):
                    next_scores[new_mask] = score
        current = next_scores
        if current:
            best = max(best, max(current.values()))
    return best


def score_prediction(
    ranked_ids: list[str], mss: dict[str, Any], k: int
) -> dict[str, float]:
    groups = list(mss.get("required_evidence_groups", []))
    if not groups:
        return {
            f"group_recall@{k}": 1.0,
            f"role_coverage@{k}": 1.0,
            f"necessity_weighted_recall@{k}": 1.0,
            f"group_ndcg@{k}": 1.0,
            f"mss_complete@{k}": 1.0,
            f"required_novelty@{k}": 1.0,
        }

    completion_ranks = [
        group_completion_rank(ranked_ids, group, k) for group in groups
    ]
    completed = [rank is not None for rank in completion_ranks]
    weights = [float(group.get("necessity_weight", 1.0)) for group in groups]
    weight_total = sum(weights)
    group_recall = sum(completed) / len(groups)
    weighted_recall = (
        sum(weight for weight, hit in zip(weights, completed) if hit) / weight_total
        if weight_total
        else 0.0
    )

    required_roles = {str(group["role"]) for group in groups}
    covered_roles = {
        str(group["role"])
        for group, hit in zip(groups, completed)
        if hit
    }
    role_coverage = len(covered_roles) / len(required_roles) if required_roles else 1.0

    dcg = sum(
        weight / math.log2(rank + 1)
        for weight, rank in zip(weights, completion_ranks)
        if rank is not None
    )
    ideal_dcg = ideal_group_dcg(groups, weights, k)
    group_ndcg = min(1.0, dcg / ideal_dcg) if ideal_dcg else 0.0

    topk = set(ranked_ids[:k])
    alternative_sets = [
        set(values) for values in mss.get("alternative_minimal_sets", [])
    ]
    grouped_complete = all(completed)
    alternative_complete = any(values <= topk for values in alternative_sets)
    mss_complete = grouped_complete or alternative_complete

    observed = set(mss.get("observed_evidence_ids", []))
    retrieved_required = {
        evidence_id
        for group in groups
        for evidence_id in group["acceptable_evidence_ids"]
        if evidence_id in topk
    }
    required_novelty = (
        len(retrieved_required - observed) / len(retrieved_required)
        if retrieved_required
        else 0.0
    )
    return {
        f"group_recall@{k}": group_recall,
        f"role_coverage@{k}": role_coverage,
        f"necessity_weighted_recall@{k}": weighted_recall,
        f"group_ndcg@{k}": group_ndcg,
        f"mss_complete@{k}": float(mss_complete),
        f"required_novelty@{k}": required_novelty,
    }


def score_rows(
    predictions: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    ks: tuple[int, ...],
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    label_by_state = {str(row["state_id"]): row for row in labels}
    if len(label_by_state) != len(labels):
        raise ValueError("duplicate state_id in MSS labels")
    per_state = []
    metrics_by_method: dict[str, list[dict[str, float]]] = defaultdict(list)
    seen_prediction_keys = set()
    for prediction in predictions:
        state_id = str(prediction["state_id"])
        method = str(prediction["method"])
        key = (state_id, method)
        if key in seen_prediction_keys:
            raise ValueError(f"duplicate prediction key: {key}")
        seen_prediction_keys.add(key)
        if state_id not in label_by_state:
            raise ValueError(f"prediction has no MSS label: {state_id}")
        ranked_ids = list(prediction["ranked_evidence_ids"])
        metrics = {}
        for k in ks:
            metrics.update(score_prediction(ranked_ids, label_by_state[state_id], k))
        row = {"state_id": state_id, "method": method, **metrics}
        per_state.append(row)
        metrics_by_method[method].append(metrics)

    summary = {}
    for method, rows in sorted(metrics_by_method.items()):
        names = sorted(rows[0])
        summary[method] = {
            "states": float(len(rows)),
            **{name: mean(row[name] for row in rows) for name in names},
        }
    return per_state, summary


__all__ = [
    "group_completion_rank",
    "ideal_group_dcg",
    "read_jsonl",
    "score_prediction",
    "score_rows",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--mss-labels", required=True, type=Path)
    parser.add_argument("--state-id-map", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--k", action="append", type=int, default=[])
    args = parser.parse_args()

    ks = tuple(sorted(set(args.k or [5, 10, 20])))
    predictions = read_jsonl(args.predictions)
    if args.state_id_map:
        mapping_rows = read_jsonl(args.state_id_map)
        source_to_release = {
            str(row["source_state_id"]): str(row["release_state_id"])
            for row in mapping_rows
        }
        if len(source_to_release) != len(mapping_rows):
            raise ValueError("duplicate source_state_id in state ID map")
        mapped_predictions = []
        for prediction in predictions:
            source_state_id = str(prediction["state_id"])
            if source_state_id not in source_to_release:
                raise ValueError(f"prediction has no state ID mapping: {source_state_id}")
            mapped = dict(prediction)
            mapped["state_id"] = source_to_release[source_state_id]
            mapped_predictions.append(mapped)
        predictions = mapped_predictions
    raw_labels = read_jsonl(args.mss_labels)
    labels = [
        dict(row["graded_labels"])
        if isinstance(row.get("graded_labels"), dict)
        else row
        for row in raw_labels
    ]
    per_state, summary = score_rows(predictions, labels, ks)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "per_state_scores.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as handle:
        for row in per_state:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
