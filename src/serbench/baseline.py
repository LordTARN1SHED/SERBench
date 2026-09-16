"""A small dependency-free BM25 starter retriever.

This is intentionally a fresh starter baseline for the public SDK.  It is not
the paper's model or a reproduction of any reported experiment.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Iterable, Mapping


_TOKEN_RE = re.compile(r"\w+", flags=re.UNICODE)
_QUERY_FIELDS = (
    "repo",
    "issue",
    "information_need",
    "current_observation",
    "current_hypothesis",
    "current_subgoal",
    "opened_files",
    "search_queries",
)


def _tokens(value: Any) -> list[str]:
    if isinstance(value, str):
        return [token.lower() for token in _TOKEN_RE.findall(value)]
    if isinstance(value, (list, tuple)):
        result: list[str] = []
        for item in value:
            result.extend(_tokens(item))
        return result
    return []


def _query(row: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for field in _QUERY_FIELDS:
        result.extend(_tokens(row.get(field)))
    return result


def _candidate_text(candidate: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    for field in ("content_excerpt", "source_path", "symbol", "language"):
        result.extend(_tokens(candidate.get(field)))
    return result


def _bm25_scores(query: list[str], documents: list[list[str]]) -> list[float]:
    if not documents:
        return []
    query_counts = Counter(query)
    document_counts = [Counter(document) for document in documents]
    lengths = [len(document) for document in documents]
    average_length = sum(lengths) / len(lengths) if lengths else 0.0
    document_frequency: Counter[str] = Counter()
    for counts in document_counts:
        document_frequency.update(counts.keys())
    total_documents = len(documents)
    k1 = 1.2
    b = 0.75
    scores: list[float] = []
    for counts, length in zip(document_counts, lengths):
        score = 0.0
        for token, query_weight in query_counts.items():
            term_frequency = counts.get(token, 0)
            if not term_frequency:
                continue
            frequency = document_frequency[token]
            inverse_document_frequency = math.log(
                1.0 + (total_documents - frequency + 0.5) / (frequency + 0.5)
            )
            normalization = (
                k1 * (1.0 - b + b * length / average_length)
                if average_length
                else k1
            )
            score += query_weight * inverse_document_frequency * (
                term_frequency * (k1 + 1.0)
            ) / (term_frequency + normalization)
        scores.append(score)
    return scores


def rank_row(row: Mapping[str, Any], k: int) -> list[str]:
    """Rank the supplied pool without automatically masking observed IDs."""

    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("k must be a positive integer")
    candidates = [
        candidate
        for candidate in row.get("candidate_evidence", [])
        if isinstance(candidate, Mapping)
        and isinstance(candidate.get("evidence_id"), str)
    ]
    documents = [_candidate_text(candidate) for candidate in candidates]
    scores = _bm25_scores(_query(row), documents)
    ranked = sorted(
        zip(scores, candidates),
        key=lambda pair: (-pair[0], str(pair[1]["evidence_id"])),
    )
    return [str(candidate["evidence_id"]) for _, candidate in ranked[:k]]


def generate_predictions(
    rows: Iterable[Mapping[str, Any]],
    *,
    k: int = 8,
    method: str = "bm25_starter",
) -> list[dict[str, Any]]:
    """Rank every item with BM25 and return prediction rows."""

    if not isinstance(method, str) or not method.strip():
        raise ValueError("method must be a non-empty string")
    result: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise ValueError(f"dataset row {index} must be an object")
        state_id = row.get("state_id")
        if not isinstance(state_id, str) or not state_id.strip():
            raise ValueError(f"dataset row {index} has an invalid state_id")
        result.append(
            {
                "state_id": state_id,
                "method": method,
                "ranked_evidence_ids": rank_row(row, k),
            }
        )
    return result


__all__ = ["generate_predictions", "rank_row"]
