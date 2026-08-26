from __future__ import annotations

import json
import re
from pathlib import Path
from statistics import mean
from typing import Any

from rag_platform.config import Settings
from rag_platform.domain.models import RetrievalEvaluationItem
from rag_platform.generation.service import GenerationService
from rag_platform.retrieval.service import RetrievalService


def load_jsonl(path: Path) -> list[RetrievalEvaluationItem]:
    with path.open(encoding="utf-8") as handle:
        return [
            RetrievalEvaluationItem.model_validate_json(line)
            for line in handle
            if line.strip() and not line.lstrip().startswith("#")
        ]


def percentile(values: list[float], value: int) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = round((value / 100) * (len(ordered) - 1))
    return ordered[index]


class EvaluationService:
    def __init__(
        self,
        settings: Settings,
        retrieval: RetrievalService,
        generation: GenerationService | None = None,
    ):
        self.settings = settings
        self.retrieval = retrieval
        self.generation = generation

    def evaluate_retrieval(self, path: Path | None = None) -> dict[str, Any]:
        items = load_jsonl(path or self.settings.evaluation.retrieval_dataset)
        hits = {1: 0, 3: 0, 5: 0}
        reciprocal_ranks: list[float] = []
        latencies: list[float] = []
        reranker_latencies: list[float] = []
        cases: list[dict[str, Any]] = []
        for item in items:
            results, latency = self.retrieval.search(item.question, top_k=max(hits))
            latencies.append(latency)
            reranker_latencies.append(self.retrieval.last_metrics.get("reranker_latency_ms", 0))
            matching_ranks = [
                rank
                for rank, result in enumerate(results, 1)
                if self._expected(result.document_id, result.filename, item.expected_document)
                and (not item.expected_pages or result.page in item.expected_pages)
            ]
            rank = min(matching_ranks, default=None)
            for cutoff in hits:
                hits[cutoff] += int(rank is not None and rank <= cutoff)
            reciprocal_ranks.append(1 / rank if rank else 0.0)
            cases.append(
                {
                    "question": item.question,
                    "expected_document": item.expected_document,
                    "rank": rank,
                    "latency_ms": latency,
                }
            )
        count = len(items)
        report = {
            "dataset": str(path or self.settings.evaluation.retrieval_dataset),
            "cases": count,
            "hit_at_1": hits[1] / count if count else 0,
            "hit_at_3": hits[3] / count if count else 0,
            "hit_at_5": hits[5] / count if count else 0,
            "mrr": mean(reciprocal_ranks) if reciprocal_ranks else 0,
            "retrieval_latency_ms_mean": mean(latencies) if latencies else 0,
            "reranker_latency_ms_mean": (mean(reranker_latencies) if reranker_latencies else 0),
            **{
                f"retrieval_latency_ms_p{value}": percentile(latencies, value)
                for value in self.settings.evaluation.latency_percentiles
            },
            "results": cases,
        }
        return report

    def evaluate_rag(self, path: Path | None = None) -> dict[str, Any]:
        if self.generation is None:
            raise ValueError("A GenerationService is required for RAG evaluation")
        items = load_jsonl(path or self.settings.evaluation.rag_dataset)
        citation_scores: list[float] = []
        faithfulness_scores: list[float] = []
        answer_relevance_scores: list[float] = []
        rejection_scores: list[float] = []
        latencies: list[float] = []
        retrieval_latencies: list[float] = []
        generation_latencies: list[float] = []
        cases: list[dict[str, Any]] = []
        for item in items:
            response = self.generation.answer(item.question)
            latencies.append(response.latency_ms)
            retrieval_latencies.append(response.retrieval_latency_ms)
            generation_latencies.append(response.generation_latency_ms)
            cited_expected = any(
                self._expected(source.document_id, source.filename, item.expected_document)
                and (not item.expected_pages or source.page in item.expected_pages)
                for source in response.sources
            )
            citation_correct = cited_expected if item.should_answer else not response.sources
            citation_scores.append(float(citation_correct))
            rejected = response.answer == self.settings.generation.insufficient_context_message
            if not item.should_answer:
                rejection_scores.append(float(rejected))
            expected_tokens = self._content_tokens(item.expected_answer or "")
            answer_tokens = self._content_tokens(response.answer)
            answer_relevance = (
                len(expected_tokens & answer_tokens) / len(expected_tokens)
                if expected_tokens
                else float(bool(response.sources) or rejected)
            )
            context = " ".join(
                chunk.text
                for chunk in self.retrieval.catalog.get_chunks_by_ids(
                    response.retrieved_chunk_ids, tenant_id=self.settings.tenant_id
                )
            )
            context_tokens = self._content_tokens(context)
            faithfulness = (
                len(answer_tokens & context_tokens) / len(answer_tokens)
                if answer_tokens and not rejected
                else float(rejected)
            )
            faithfulness_scores.append(faithfulness)
            answer_relevance_scores.append(answer_relevance)
            cases.append(
                {
                    "question": item.question,
                    "should_answer": item.should_answer,
                    "rejected": rejected,
                    "citation_correct": citation_correct,
                    "faithfulness": faithfulness,
                    "answer_relevance": answer_relevance,
                    "latency_ms": response.latency_ms,
                }
            )
        report = {
            "dataset": str(path or self.settings.evaluation.rag_dataset),
            "cases": len(items),
            "groundedness": mean(faithfulness_scores) if faithfulness_scores else 0,
            "faithfulness": mean(faithfulness_scores) if faithfulness_scores else 0,
            "answer_relevance": (mean(answer_relevance_scores) if answer_relevance_scores else 0),
            "citation_correctness": mean(citation_scores) if citation_scores else 0,
            "unsupported_question_rejection": mean(rejection_scores) if rejection_scores else 0,
            "end_to_end_latency_ms_mean": mean(latencies) if latencies else 0,
            "retrieval_latency_ms_mean": (mean(retrieval_latencies) if retrieval_latencies else 0),
            "generation_latency_ms_mean": (
                mean(generation_latencies) if generation_latencies else 0
            ),
            "results": cases,
        }
        return report

    def write_report(self, name: str, report: dict[str, Any]) -> Path:
        directory = self.settings.evaluation.report_dir
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{name}.json"
        target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return target

    @staticmethod
    def _expected(document_id: str, filename: str, expected: str) -> bool:
        return expected in {document_id, filename, Path(filename).stem}

    @staticmethod
    def _content_tokens(value: str) -> set[str]:
        stop = {"the", "a", "an", "and", "or", "to", "of", "is", "in", "for", "that"}
        return {token for token in re.findall(r"[a-z0-9-]+", value.lower()) if token not in stop}
