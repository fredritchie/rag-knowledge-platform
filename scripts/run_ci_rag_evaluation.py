#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

from rag_platform.config import Settings
from rag_platform.domain.models import ChunkRecord, DocumentRecord
from rag_platform.domain.states import DocumentStatus
from rag_platform.evaluation.quality_gate import evaluate_quality_gate
from rag_platform.evaluation.service import EvaluationService, load_jsonl
from rag_platform.generation.service import GenerationService
from rag_platform.retrieval.embeddings import DeterministicEmbedder
from rag_platform.retrieval.reranker import NoOpReranker
from rag_platform.retrieval.service import RetrievalService
from rag_platform.retrieval.vector_store import InMemoryVectorStore
from rag_platform.storage.sqlite import SQLiteCatalog

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "datasets" / "ci-golden.jsonl"
DEFAULT_BASELINE = ROOT / "evaluation" / "baselines" / "ci-quality.json"

SOURCE_TEXT = {
    "NIST-SP-800-207.pdf": "Zero trust removes implicit trust based on network location.",
    "RAG-foundations.pdf": (
        "Retrieval augmented generation combines retrieved evidence with language generation."
    ),
    "Kubernetes-scheduling.pdf": (
        "Tolerations allow matching pods to schedule onto tainted nodes."
    ),
}

DISTRACTORS = {
    "Storage-handbook.pdf": "Object storage lifecycle policies retain archived binary objects.",
    "Networking-guide.pdf": "Public route tables send internet traffic through a gateway.",
    "Database-notes.pdf": "Relational databases use transactions and structured query languages.",
    "Monitoring-guide.pdf": "Metrics dashboards display service latency and resource utilization.",
    "Queueing-guide.pdf": "Message queues decouple producers from asynchronous consumers.",
}


class DeterministicQualityGateLLM:
    """Offline CI adapter with fixed answers grounded in the supplied prompt context."""

    model_version = "ci-grounded-v1"

    def __init__(self, answers: dict[str, str]):
        self.answers = answers

    def generate(self, *, system: str, prompt: str) -> str:
        del system
        for question, answer in self.answers.items():
            if question in prompt:
                if answer not in prompt:
                    raise RuntimeError("Expected evidence was not retrieved into the prompt")
                return f"{answer} [SOURCE 1]"
        raise RuntimeError("CI golden question has no deterministic answer")

    def stream(self, *, system: str, prompt: str) -> Iterator[str]:
        yield self.generate(system=system, prompt=prompt)


def _settings(data_dir: Path) -> Settings:
    return Settings.model_validate(
        {
            "data_dir": data_dir,
            "embedding": {
                "provider": "deterministic",
                "model": "sha256-token-hash",
                "model_version": "ci-hash-v1",
                "dimension": 128,
                "query_prefix": "",
            },
            "retrieval": {
                "mode": "hybrid",
                "top_k": 3,
                "candidate_k": 10,
                "similarity_threshold": -1,
            },
            "reranker": {"enabled": False, "provider": "none"},
            "generation": {
                "model": "ci-grounded",
                "model_version": "ci-grounded-v1",
                "prompt_dir": ROOT / "prompts" / "rag",
                "temperature": 0,
            },
        }
    )


def _seed_retrieval(settings: Settings) -> RetrievalService:
    catalog = SQLiteCatalog(settings.database_path)
    documents = {**SOURCE_TEXT, **DISTRACTORS}
    for index, (filename, text) in enumerate(documents.items()):
        page = {"NIST-SP-800-207.pdf": 4, "Kubernetes-scheduling.pdf": 2}.get(filename, 1)
        document_id = f"ci-doc-{index}"
        document = DocumentRecord(
            document_id=document_id,
            filename=filename,
            source="ci-golden",
            checksum_sha256=f"ci-{index:02d}",
            file_size_bytes=len(text.encode()),
            page_count=page,
            parser_version="ci",
            chunker_version="ci-v1",
            status=DocumentStatus.ACTIVE,
        )
        catalog.upsert_document(document)
        catalog.replace_chunks(
            document_id,
            [
                ChunkRecord(
                    chunk_id=f"ci-chunk-{index}",
                    document_id=document_id,
                    filename=filename,
                    page=page,
                    chunk_index=0,
                    page_chunk_index=0,
                    text=text,
                    source="ci-golden",
                    document_version=1,
                    checksum_sha256=f"ci-{index:02d}",
                    chunker_version="ci-v1",
                    char_start=0,
                    char_end=len(text),
                )
            ],
        )

    retrieval = RetrievalService(
        settings,
        catalog=catalog,
        embedder=DeterministicEmbedder(settings.embedding),
        vector_store=InMemoryVectorStore(),
        reranker=NoOpReranker(),
    )
    retrieval.index_all()
    return retrieval


def run(dataset: Path, baseline_path: Path, output_dir: Path, work_dir: Path) -> bool:
    settings = _settings(work_dir)
    retrieval = _seed_retrieval(settings)
    answers = {
        item.question: item.expected_answer or ""
        for item in load_jsonl(dataset)
        if item.should_answer
    }
    generation = GenerationService(
        settings,
        retrieval=retrieval,
        llm=DeterministicQualityGateLLM(answers),
    )
    evaluator = EvaluationService(settings, retrieval, generation)
    retrieval_report = evaluator.evaluate_retrieval(dataset)
    rag_report = evaluator.evaluate_rag(dataset)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    gate = evaluate_quality_gate(retrieval_report, rag_report, baseline)

    output_dir.mkdir(parents=True, exist_ok=True)
    reports = {
        "retrieval-report.json": retrieval_report,
        "rag-report.json": rag_report,
        "quality-gate.json": gate,
    }
    for filename, report in reports.items():
        (output_dir / filename).write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    print(json.dumps(gate, indent=2, sort_keys=True))
    return bool(gate["passed"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic PR RAG quality gate")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation/reports/ci"))
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args()

    if args.work_dir:
        return 0 if run(args.dataset, args.baseline, args.output_dir, args.work_dir) else 1
    with tempfile.TemporaryDirectory(prefix="rag-ci-evaluation-") as directory:
        return 0 if run(args.dataset, args.baseline, args.output_dir, Path(directory)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
