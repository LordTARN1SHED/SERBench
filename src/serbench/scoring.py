"""Validated prediction loading and the public SERBench scoring wrapper."""

from __future__ import annotations

import json
import math
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ._reference_scorer import score_rows as _reference_score_rows
from .data import DataError, read_jsonl


class ScoringError(ValueError):
    """Base class for malformed prediction or label inputs."""


class ValidationError(ScoringError):
    """Raised when a prediction/label file violates the release contract."""


def _nonempty_string(value: Any, field: str, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{where}: {field} must be a non-empty string")
    return value


def _as_rows(
    rows: Iterable[Mapping[str, Any]] | os.PathLike[str] | str,
    *,
    kind: str,
) -> list[dict[str, Any]]:
    if isinstance(rows, (str, os.PathLike)):
        try:
            loaded = read_jsonl(rows)
        except DataError as exc:
            raise ValidationError(f"could not read {kind} file {rows}: {exc}") from exc
        return loaded
    result: list[dict[str, Any]] = []
    try:
        iterator = iter(rows)
    except TypeError as exc:
        raise ValidationError(f"{kind} must be an iterable of JSON objects") from exc
    for index, row in enumerate(iterator, start=1):
        if not isinstance(row, Mapping):
            raise ValidationError(f"{kind} row {index} must be a JSON object")
        result.append(dict(row))
    return result


def _unwrap_label(row: Mapping[str, Any], index: int) -> dict[str, Any]:
    nested = row.get("graded_labels")
    if nested is not None:
        if not isinstance(nested, Mapping):
            raise ValidationError(f"label row {index}: graded_labels must be an object")
        value = dict(nested)
        # A few organizer exports keep state_id on the envelope.  Supporting
        # that harmless shape does not change the official formulas.
        if "state_id" not in value and "state_id" in row:
            value["state_id"] = row["state_id"]
        return value
    return dict(row)


def _validate_string_list(value: Any, field: str, where: str, *, nonempty: bool) -> list[str]:
    if not isinstance(value, list):
        raise ValidationError(f"{where}: {field} must be a JSON list")
    if nonempty and not value:
        raise ValidationError(f"{where}: {field} must not be empty")
    seen: set[str] = set()
    result: list[str] = []
    for position, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValidationError(
                f"{where}: {field}[{position}] must be a non-empty string"
            )
        if item in seen:
            raise ValidationError(f"{where}: duplicate ID {item!r} in {field}")
        seen.add(item)
        result.append(item)
    return result


def _dataset_indexes(
    dataset: Iterable[Mapping[str, Any]],
) -> tuple[set[str], dict[str, set[str]], dict[str, set[str]]]:
    """Return state IDs, candidate IDs, and observed IDs after schema checks."""

    state_ids: set[str] = set()
    candidates: dict[str, set[str]] = {}
    observed: dict[str, set[str]] = {}
    for index, raw_row in enumerate(dataset, start=1):
        if not isinstance(raw_row, Mapping):
            raise ValidationError(f"dataset row {index} must be a JSON object")
        where = f"dataset row {index}"
        state_id = _nonempty_string(raw_row.get("state_id"), "state_id", where)
        if state_id in state_ids:
            raise ValidationError(f"{where}: duplicate state_id {state_id!r}")
        state_ids.add(state_id)

        candidate_rows = raw_row.get("candidate_evidence")
        if not isinstance(candidate_rows, list):
            raise ValidationError(f"{where}: candidate_evidence must be a JSON list")
        candidate_ids: set[str] = set()
        for candidate_index, candidate in enumerate(candidate_rows):
            if not isinstance(candidate, Mapping):
                raise ValidationError(
                    f"{where}: candidate_evidence[{candidate_index}] must be an object"
                )
            evidence_id = _nonempty_string(
                candidate.get("evidence_id"),
                "evidence_id",
                f"{where} candidate_evidence[{candidate_index}]",
            )
            if evidence_id in candidate_ids:
                raise ValidationError(
                    f"{where}: duplicate candidate evidence_id {evidence_id!r}"
                )
            candidate_ids.add(evidence_id)
        observed_ids = _validate_string_list(
            raw_row.get("observed_evidence_ids", []),
            "observed_evidence_ids",
            where,
            nonempty=False,
        )
        candidates[state_id] = candidate_ids
        observed[state_id] = set(observed_ids)
    if not state_ids:
        raise ValidationError("dataset is empty")
    return state_ids, candidates, observed


def validate_labels(
    labels: Iterable[Mapping[str, Any]] | os.PathLike[str] | str,
    *,
    expected_state_ids: set[str] | Sequence[str] | None = None,
    candidate_ids_by_state: Mapping[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    """Validate and normalize official or organizer-provided label rows.

    The returned rows are safe to pass to the unchanged reference scorer.  A
    label set must contain at least one state and each state must contain one
    or more well-formed required evidence groups.  Alternative branches are
    optional, but every branch that is present must be non-empty and unique.
    """

    raw_rows = _as_rows(labels, kind="labels")
    if not raw_rows:
        raise ValidationError("labels must contain at least one state")
    expected = set(expected_state_ids) if expected_state_ids is not None else None
    normalized: list[dict[str, Any]] = []
    seen_states: set[str] = set()
    for index, raw_row in enumerate(raw_rows, start=1):
        row = _unwrap_label(raw_row, index)
        where = f"label row {index}"
        state_id = _nonempty_string(row.get("state_id"), "state_id", where)
        if state_id in seen_states:
            raise ValidationError(f"duplicate label state_id {state_id!r}")
        seen_states.add(state_id)
        if expected is not None and state_id not in expected:
            raise ValidationError(f"label has unknown state_id {state_id!r}")

        groups = row.get("required_evidence_groups")
        if not isinstance(groups, list) or not groups:
            raise ValidationError(
                f"{where}: required_evidence_groups must be a non-empty list"
            )
        group_ids: set[str] = set()
        clean_groups: list[dict[str, Any]] = []
        candidate_ids = (
            candidate_ids_by_state.get(state_id)
            if candidate_ids_by_state is not None
            else None
        )
        for group_index, raw_group in enumerate(groups, start=1):
            group_where = f"{where} required_evidence_groups[{group_index - 1}]"
            if not isinstance(raw_group, Mapping):
                raise ValidationError(f"{group_where} must be an object")
            group = dict(raw_group)
            role = _nonempty_string(group.get("role"), "role", group_where)
            group_id = group.get("group_id")
            if group_id is not None:
                group_id = _nonempty_string(group_id, "group_id", group_where)
                if group_id in group_ids:
                    raise ValidationError(f"{group_where}: duplicate group_id {group_id!r}")
                group_ids.add(group_id)
            acceptable = _validate_string_list(
                group.get("acceptable_evidence_ids"),
                "acceptable_evidence_ids",
                group_where,
                nonempty=True,
            )
            if "minimum_required" not in group:
                raise ValidationError(f"{group_where}: missing minimum_required")
            minimum = group.get("minimum_required")
            if isinstance(minimum, bool) or not isinstance(minimum, int) or minimum < 1:
                raise ValidationError(
                    f"{group_where}: minimum_required must be a positive integer"
                )
            if minimum > len(acceptable):
                raise ValidationError(
                    f"{group_where}: minimum_required exceeds acceptable evidence count"
                )
            if "necessity_weight" not in group:
                raise ValidationError(f"{group_where}: missing necessity_weight")
            weight = group.get("necessity_weight")
            if isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ValidationError(f"{group_where}: necessity_weight must be a number")
            if not math.isfinite(float(weight)) or float(weight) <= 0:
                raise ValidationError(
                    f"{group_where}: necessity_weight must be finite and positive"
                )
            if candidate_ids is not None:
                unknown = sorted(set(acceptable) - candidate_ids)
                if unknown:
                    raise ValidationError(
                        f"{group_where}: unknown candidate evidence ID(s): {unknown}"
                    )
            clean_groups.append(group)

        alternatives = row.get("alternative_minimal_sets", [])
        if not isinstance(alternatives, list):
            raise ValidationError(f"{where}: alternative_minimal_sets must be a list")
        clean_alternatives: list[list[str]] = []
        for branch_index, branch in enumerate(alternatives):
            branch_where = f"{where} alternative_minimal_sets[{branch_index}]"
            clean_branch = _validate_string_list(
                branch,
                "branch",
                branch_where,
                nonempty=True,
            )
            if candidate_ids is not None:
                unknown = sorted(set(clean_branch) - candidate_ids)
                if unknown:
                    raise ValidationError(
                        f"{branch_where}: unknown candidate evidence ID(s): {unknown}"
                    )
            clean_alternatives.append(clean_branch)

        optional = _validate_string_list(
            row.get("optional_evidence_ids", []),
            "optional_evidence_ids",
            where,
            nonempty=False,
        )
        if candidate_ids is not None:
            unknown = sorted(set(optional) - candidate_ids)
            if unknown:
                raise ValidationError(
                    f"{where}: unknown candidate evidence ID(s) in optional_evidence_ids: {unknown}"
                )
        observed = _validate_string_list(
            row.get("observed_evidence_ids", []),
            "observed_evidence_ids",
            where,
            nonempty=False,
        )
        clean = dict(row)
        clean["state_id"] = state_id
        clean["required_evidence_groups"] = clean_groups
        clean["alternative_minimal_sets"] = clean_alternatives
        clean["optional_evidence_ids"] = optional
        clean["observed_evidence_ids"] = observed
        normalized.append(clean)

    if expected is not None:
        missing = sorted(expected - seen_states)
        if missing:
            raise ValidationError(f"labels are missing state_id(s): {missing}")
    return normalized


def validate_predictions(
    predictions: Iterable[Mapping[str, Any]] | os.PathLike[str] | str,
    dataset: Iterable[Mapping[str, Any]],
    *,
    labels: Iterable[Mapping[str, Any]] | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate predictions against item candidates while preserving rank slots.

    By default every method must provide exactly one prediction for every
    dataset state.  Set ``strict=False`` only for an explicitly partial local
    analysis; the CLI keeps strict mode enabled by default to prevent subset
    inflation.  Observed candidate IDs remain valid ranked slots: they are
    never silently removed or backfilled before scoring.
    """

    dataset_rows = list(dataset)
    state_ids, candidates, observed = _dataset_indexes(dataset_rows)
    normalized_labels: list[dict[str, Any]] | None = None
    if labels is not None:
        normalized_labels = validate_labels(
            labels,
            expected_state_ids=state_ids,
            candidate_ids_by_state=candidates,
        )
        for label in normalized_labels:
            sid = label['state_id']
            if set(label.get('observed_evidence_ids', [])) != observed[sid]:
                raise ValidationError(f"label {sid}: observed IDs disagree with dataset")
            gold = {e for g in label['required_evidence_groups'] for e in g['acceptable_evidence_ids']}
            gold.update(e for branch in label.get('alternative_minimal_sets', []) for e in branch)
            if gold & observed[sid]:
                raise ValidationError(f"label {sid}: residual gold overlaps observed evidence")

    prediction_rows = _as_rows(predictions, kind="predictions")
    if not prediction_rows:
        raise ValidationError("predictions must contain at least one row")
    seen_keys: set[tuple[str, str]] = set()
    method_states: dict[str, set[str]] = defaultdict(set)
    total_candidates = sum(len(values) for values in candidates.values())
    for index, row in enumerate(prediction_rows, start=1):
        where = f"prediction row {index}"
        state_id = _nonempty_string(row.get("state_id"), "state_id", where)
        method = _nonempty_string(row.get("method"), "method", where)
        if state_id not in state_ids:
            raise ValidationError(f"{where}: unknown state_id {state_id!r}")
        key = (state_id, method)
        if key in seen_keys:
            raise ValidationError(
                f"duplicate prediction key (state_id={state_id!r}, method={method!r})"
            )
        seen_keys.add(key)
        ranked = row.get("ranked_evidence_ids")
        if not isinstance(ranked, list):
            raise ValidationError(f"{where}: ranked_evidence_ids must be a JSON list")
        ranked_ids = _validate_string_list(
            ranked,
            "ranked_evidence_ids",
            where,
            nonempty=False,
        )
        unknown = sorted(set(ranked_ids) - candidates[state_id])
        if unknown:
            raise ValidationError(
                f"{where}: evidence ID(s) are not candidates for {state_id!r}: {unknown}"
            )
        method_states[method].add(state_id)

    if strict:
        for method, states in sorted(method_states.items()):
            missing = sorted(state_ids - states)
            if missing:
                raise ValidationError(
                    f"method {method!r} is missing prediction(s) for state_id(s): {missing}"
                )

    return {
        "valid": True,
        "states": len(state_ids),
        "methods": len(method_states),
        "prediction_count": len(prediction_rows),
        "candidate_count": total_candidates,
        "per_method": {
            method: len(states) for method, states in sorted(method_states.items())
        },
        "strict": strict,
        "labels_checked": normalized_labels is not None,
    }


def _normalize_ks(ks: Iterable[int] | int) -> tuple[int, ...]:
    if isinstance(ks, int) and not isinstance(ks, bool):
        values = [ks]
    else:
        values = list(ks)
    if not values:
        raise ScoringError("at least one positive k is required")
    clean: list[int] = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ScoringError("all k values must be positive integers")
        clean.append(value)
    return tuple(sorted(set(clean)))


def _label_candidate_indexes(
    labels: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    candidate_ids: dict[str, set[str]] = {}
    observed: dict[str, set[str]] = {}
    for row in labels:
        state_id = str(row["state_id"])
        values: set[str] = set()
        for group in row["required_evidence_groups"]:
            values.update(group["acceptable_evidence_ids"])
        for branch in row.get("alternative_minimal_sets", []):
            values.update(branch)
        optional = row.get("optional_evidence_ids", [])
        if isinstance(optional, list):
            values.update(value for value in optional if isinstance(value, str))
        observed_values = {
            value for value in row.get("observed_evidence_ids", []) if isinstance(value, str)
        }
        values.update(observed_values)
        candidate_ids[state_id] = values
        observed[state_id] = observed_values
    return candidate_ids, observed


def score_predictions(
    predictions: Iterable[Mapping[str, Any]] | os.PathLike[str] | str,
    labels: Iterable[Mapping[str, Any]] | os.PathLike[str] | str,
    ks: Iterable[int] | int = (5, 8),
    *,
    dataset: Iterable[Mapping[str, Any]] | None = None,
    strict: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
    """Validate and score predictions, returning ``(per_state, summary)``.

    ``dataset`` is strongly recommended and is required by the CLI.  When it
    is omitted, candidate membership is conservatively derived from label
    evidence IDs so the function remains useful for small custom fixtures.
    """

    clean_ks = _normalize_ks(ks)
    raw_labels = _as_rows(labels, kind="labels")
    prediction_rows = _as_rows(predictions, kind="predictions")

    if dataset is not None:
        dataset_rows = list(dataset)
        state_ids, candidates, _ = _dataset_indexes(dataset_rows)
        clean_labels = validate_labels(
            raw_labels,
            expected_state_ids=state_ids,
            candidate_ids_by_state=candidates,
        )
        validate_predictions(
            prediction_rows,
            dataset_rows,
            labels=clean_labels,
            strict=strict,
        )
    else:
        # Validate first, then use all labelled evidence as the minimal custom
        # fixture's candidate universe.
        clean_labels = validate_labels(raw_labels)
        label_candidates, label_observed = _label_candidate_indexes(clean_labels)
        synthetic_dataset = [
            {
                "state_id": state_id,
                "candidate_evidence": [
                    {"evidence_id": evidence_id} for evidence_id in sorted(values)
                ],
                "observed_evidence_ids": sorted(label_observed.get(state_id, set())),
            }
            for state_id, values in label_candidates.items()
        ]
        validate_predictions(
            prediction_rows,
            synthetic_dataset,
            labels=clean_labels,
            strict=strict,
        )

    try:
        return _reference_score_rows(prediction_rows, clean_labels, clean_ks)
    except (KeyError, TypeError, ValueError) as exc:
        # Inputs have already been checked; retain a stable public exception
        # type if a custom extension still violates the reference contract.
        raise ScoringError(f"could not score predictions: {exc}") from exc


def write_score_outputs(
    per_state: Sequence[Mapping[str, Any]],
    summary: Mapping[str, Any],
    output_dir: str | os.PathLike[str],
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write the standard score files, refusing accidental overwrites."""

    directory = Path(output_dir)
    per_state_path = directory / "per_state_scores.jsonl"
    summary_path = directory / "summary.json"
    if not overwrite:
        existing = [path for path in (per_state_path, summary_path) if path.exists()]
        if existing:
            names = ", ".join(str(path) for path in existing)
            raise ScoringError(
                f"refusing to overwrite existing score output(s): {names}; "
                "pass --overwrite to replace them"
            )
    directory.mkdir(parents=True, exist_ok=True)
    with per_state_path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in per_state:
            handle.write(json.dumps(dict(row), sort_keys=True) + "\n")
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return per_state_path, summary_path


def read_predictions(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    """Read prediction JSONL; schema validation occurs in ``validate_predictions``."""

    return _as_rows(path, kind="predictions")


__all__ = [
    "ScoringError",
    "ValidationError",
    "read_predictions",
    "score_predictions",
    "validate_labels",
    "validate_predictions",
    "write_score_outputs",
]
