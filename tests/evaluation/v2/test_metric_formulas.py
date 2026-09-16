from __future__ import annotations

import math

from tests.evaluation.v2.metrics import (
    citation_correctness,
    claim_coverage,
    macro_f1,
    ndcg_at_k,
    recall_at_k,
)


def test_recall_at_k_uses_relevant_items_in_the_top_k() -> None:
    assert recall_at_k(["a", "x", "b"], {"a", "b"}, 2) == 0.5


def test_ndcg_at_k_rewards_relevant_items_earlier() -> None:
    assert ndcg_at_k(["a", "b"], {"a", "b"}, 2) == 1.0
    assert ndcg_at_k(["b", "a"], {"a", "b"}, 2) == 1.0
    assert ndcg_at_k(["x", "a"], {"a", "b"}, 2) < 1.0


def test_macro_f1_averages_per_label_f1() -> None:
    value = macro_f1(["a", "a", "b"], ["a", "b", "b"], labels=("a", "b"))
    assert math.isclose(value, (2 / 3 + 2 / 3) / 2)


def test_claim_coverage_and_citation_correctness_are_zero_for_empty_inputs() -> None:
    assert claim_coverage([], {"c1"}) == 0.0
    assert citation_correctness([], {"c1": {"e1"}}) == 0.0


def test_citation_correctness_requires_supported_claim_and_matching_evidence() -> None:
    citations = [
        {"claim_id": "c1", "evidence_id": "e1"},
        {"claim_id": "c1", "evidence_id": "wrong"},
        {"claim_id": "unsupported", "evidence_id": "e1"},
    ]
    assert citation_correctness(citations, {"c1": {"e1"}}) == 1 / 3
