"""Deterministic evaluation metrics used by the V3 quality gates."""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence


def recall_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    if k <= 0 or not set(relevant):
        return 0.0
    relevant_set = set(relevant)
    return len(set(retrieved[:k]) & relevant_set) / len(relevant_set)


def ndcg_at_k(retrieved: Sequence[str], relevant: Iterable[str], k: int) -> float:
    relevant_set = set(relevant)
    if k <= 0 or not relevant_set:
        return 0.0

    def gain(index: int, item: str) -> float:
        return (1.0 if item in relevant_set else 0.0) / math.log2(index + 2)

    dcg = sum(gain(index, item) for index, item in enumerate(retrieved[:k]))
    ideal = sum(
        1.0 / math.log2(index + 2) for index in range(min(k, len(relevant_set)))
    )
    return dcg / ideal if ideal else 0.0


def macro_f1(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    labels: Iterable[str] | None = None,
) -> float:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred must have the same length")
    label_set = tuple(labels or sorted(set(y_true) | set(y_pred)))
    if not label_set:
        return 0.0
    scores: list[float] = []
    for label in label_set:
        tp = sum(
            actual == label and predicted == label
            for actual, predicted in zip(y_true, y_pred)
        )
        fp = sum(
            actual != label and predicted == label
            for actual, predicted in zip(y_true, y_pred)
        )
        fn = sum(
            actual == label and predicted != label
            for actual, predicted in zip(y_true, y_pred)
        )
        denominator = 2 * tp + fp + fn
        scores.append(2 * tp / denominator if denominator else 0.0)
    return sum(scores) / len(scores)


def claim_coverage(claim_ids: Sequence[str], supported_ids: Iterable[str]) -> float:
    if not claim_ids:
        return 0.0
    supported = set(supported_ids)
    return sum(claim_id in supported for claim_id in claim_ids) / len(claim_ids)


def citation_correctness(
    citations: Sequence[Mapping[str, str]],
    claim_evidence: Mapping[str, Iterable[str]],
) -> float:
    if not citations:
        return 0.0
    correct = 0
    for citation in citations:
        claim_id = citation.get("claim_id")
        evidence_id = citation.get("evidence_id")
        if (
            claim_id
            and evidence_id
            and evidence_id in set(claim_evidence.get(claim_id, ()))
        ):
            correct += 1
    return correct / len(citations)
