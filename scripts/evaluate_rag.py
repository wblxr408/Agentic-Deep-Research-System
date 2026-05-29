"""
Run offline layered RAG evaluation against a labeled dataset.

Example:
    D:\DeepIntel\.venv\Scripts\python.exe scripts\evaluate_rag.py ^
        --dataset metrics\rag_evaluation\sample_dataset.jsonl ^
        --group finance ^
        --top-k 5
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.agents.rag import RAGAgent
from app.rag.evaluation import RAGOfflineEvaluator, load_eval_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run offline RAG evaluation")
    parser.add_argument("--dataset", required=True, help="Path to JSON/JSONL benchmark dataset")
    parser.add_argument("--group", default=None, help="Optional RAG source group filter")
    parser.add_argument("--top-k", type=int, default=None, help="Override dataset top_k for all examples")
    parser.add_argument(
        "--with-generation",
        action="store_true",
        help="Also run generation-layer scoring with an LLM judge",
    )
    parser.add_argument(
        "--judge-model",
        default="gpt-4o-mini",
        help="Judge model name for generation-layer scoring",
    )
    args = parser.parse_args()

    examples = load_eval_dataset(args.dataset)
    if args.top_k is not None:
        for example in examples:
            example.top_k = args.top_k

    evaluator = RAGOfflineEvaluator(
        retrieval_runner=RAGAgent(),
        judge_model=args.judge_model,
    )
    metrics = evaluator.evaluate_dataset(
        examples,
        group=args.group,
        run_generation_eval=args.with_generation,
    )

    output_path = Path("metrics/rag_evaluation/latest_summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
