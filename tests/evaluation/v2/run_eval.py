"""Run deterministic V2 quality-gate evaluation over versioned JSONL fixtures."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, stdev
from typing import Any

from .metrics import (
    citation_correctness,
    claim_coverage,
    macro_f1,
    ndcg_at_k,
    recall_at_k,
)

ROOT = Path(__file__).parent
SUITES = ("planner", "router", "retrieval", "citation", "tool_calling")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict) or not value.get("id"):
            raise ValueError(f"invalid record at {path}:{line_number}")
        records.append(value)
    return records


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": 0.0, "ci95": [0.0, 0.0], "sample_count": 0}
    average = mean(values)
    if len(values) < 2:
        margin = 0.0
    else:
        margin = 1.96 * stdev(values) / math.sqrt(len(values))
    return {
        "mean": round(average, 6),
        "ci95": [
            round(max(0.0, average - margin), 6),
            round(min(1.0, average + margin), 6),
        ],
        "sample_count": len(values),
    }


def evaluate_suite(name: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    categories = Counter(
        str(record.get("category", "uncategorized")) for record in records
    )
    if name in {"planner", "router", "tool_calling"}:
        labels = sorted(
            {str(record.get("true_label")) for record in records}
            | {str(record.get("predicted_label")) for record in records}
        )
        metrics = {
            "macro_f1": _summary(
                [
                    macro_f1(
                        [str(record.get("true_label")) for record in records],
                        [str(record.get("predicted_label")) for record in records],
                        labels=labels,
                    )
                ]
            )
        }
    elif name == "retrieval":
        metrics = {
            "recall_at_10": _summary(
                [
                    recall_at_k(
                        record.get("retrieved", []), record.get("relevant", []), 10
                    )
                    for record in records
                ]
            ),
            "ndcg_at_10": _summary(
                [
                    ndcg_at_k(
                        record.get("retrieved", []), record.get("relevant", []), 10
                    )
                    for record in records
                ]
            ),
        }
    elif name == "citation":
        metrics = {
            "claim_coverage": _summary(
                [
                    claim_coverage(
                        record.get("claims", []), record.get("supported_claims", [])
                    )
                    for record in records
                ]
            ),
            "citation_correctness": _summary(
                [
                    citation_correctness(
                        record.get("citations", []), record.get("claim_evidence", {})
                    )
                    for record in records
                ]
            ),
        }
    else:
        raise ValueError(f"unsupported suite: {name}")
    return {
        "sample_count": len(records),
        "category_counts": dict(sorted(categories.items())),
        "metrics": metrics,
    }


def build_report(
    suite: str,
    *,
    model_version: str = "fixture",
    prompt_version: str = "v2",
    schema_version: str = "v2",
    index_version: str = "fixture",
) -> dict[str, Any]:
    selected = SUITES if suite == "all" else (suite,)
    suites = {
        name: evaluate_suite(name, _load_jsonl(ROOT / "datasets" / f"{name}.jsonl"))
        for name in selected
    }
    return {
        "dataset_version": "warehouse-v3-golden-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "sample_count": sum(item["sample_count"] for item in suites.values()),
        "model_version": model_version,
        "prompt_version": prompt_version,
        "schema_version": schema_version,
        "index_version": index_version,
        "suites": suites,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("all", *SUITES), default="all")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--model-version", default="fixture")
    parser.add_argument("--prompt-version", default="v2")
    parser.add_argument("--schema-version", default="v2")
    parser.add_argument("--index-version", default="fixture")
    args = parser.parse_args()
    report = build_report(
        args.suite,
        model_version=args.model_version,
        prompt_version=args.prompt_version,
        schema_version=args.schema_version,
        index_version=args.index_version,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
