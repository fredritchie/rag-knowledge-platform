from __future__ import annotations

import json
from pathlib import Path

import pytest

from rag_platform.config import Settings, load_settings
from rag_platform.domain.models import ChunkRecord, DocumentRecord
from rag_platform.domain.states import DocumentStatus
from rag_platform.evaluation.service import EvaluationService
from rag_platform.generation.service import GenerationService
from rag_platform.retrieval.embeddings import DeterministicEmbedder
from rag_platform.retrieval.reranker import NoOpReranker
from rag_platform.retrieval.service import RetrievalService
from rag_platform.retrieval.vector_store import InMemoryVectorStore
from rag_platform.storage.sqlite import SQLiteCatalog


class FakeLLM:
    model_version = "fake-v1"

    def generate(self, *, system: str, prompt: str) -> str:
        assert "zero trust" in prompt.lower()
        return "Zero trust removes implicit network trust. [SOURCE 1]"

    def stream(self, *, system: str, prompt: str):
        yield "Grounded "
        yield "answer [SOURCE 1]"


def build_retrieval(tmp_path: Path) -> tuple[Settings, RetrievalService]:
    settings = Settings.model_validate(
        {
            "data_dir": tmp_path / "data",
            "embedding": {
                "provider": "deterministic",
                "model": "hash",
                "model_version": "hash-v1",
                "dimension": 64,
                "query_prefix": "",
            },
            "retrieval": {
                "mode": "hybrid",
                "top_k": 5,
                "candidate_k": 20,
                "similarity_threshold": -1,
            },
            "reranker": {"enabled": False, "provider": "none"},
            "generation": {"prompt_dir": Path("prompts/rag")},
        }
    )
    catalog = SQLiteCatalog(settings.database_path)
    document = DocumentRecord(
        document_id="doc_nist",
        filename="NIST-SP-800-207.pdf",
        source="test",
        checksum_sha256="abc",
        file_size_bytes=100,
        page_count=4,
        parser_version="test",
        chunker_version="paragraph-char-v2",
        status=DocumentStatus.ACTIVE,
    )
    catalog.upsert_document(document)
    catalog.replace_chunks(
        document.document_id,
        [
            ChunkRecord(
                chunk_id="chk_zero_trust",
                document_id=document.document_id,
                filename=document.filename,
                page=4,
                chunk_index=0,
                page_chunk_index=0,
                text="Zero trust architecture removes implicit trust based on network location.",
                source=document.source,
                document_version=1,
                checksum_sha256="abc",
                chunker_version="paragraph-char-v2",
                char_start=0,
                char_end=73,
            ),
            ChunkRecord(
                chunk_id="chk_unrelated",
                document_id=document.document_id,
                filename=document.filename,
                page=2,
                chunk_index=1,
                page_chunk_index=0,
                text="A glossary of document formatting conventions.",
                source=document.source,
                document_version=1,
                checksum_sha256="abc",
                chunker_version="paragraph-char-v2",
                char_start=0,
                char_end=47,
            ),
        ],
    )
    embedder = DeterministicEmbedder(settings.embedding)
    store = InMemoryVectorStore()
    retrieval = RetrievalService(
        settings,
        catalog=catalog,
        embedder=embedder,
        vector_store=store,
        reranker=NoOpReranker(),
    )
    retrieval.index_document(document.document_id)
    return settings, retrieval


def test_configuration_loads_yaml_and_nested_environment_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "rag.yaml"
    path.write_text("retrieval:\n  top_k: 3\nchunking:\n  size: 800\n  overlap: 75\n")
    monkeypatch.setenv("RAG__RETRIEVAL__TOP_K", "10")
    settings = load_settings(path)
    assert settings.retrieval.top_k == 10
    assert settings.chunking.size == 800


def test_index_payload_and_hybrid_search(tmp_path: Path) -> None:
    settings, retrieval = build_retrieval(tmp_path)
    point = retrieval.vector_store.points["chk_zero_trust"]
    assert point.payload == {
        "tenant_id": "default",
        "document_id": "doc_nist",
        "document_version": 1,
        "source": "test",
        "page": 4,
        "filename": "NIST-SP-800-207.pdf",
        "chunk_index": 0,
        "embedding_model_version": "hash-v1",
        "chunker_version": "paragraph-char-v2",
        "text": "Zero trust architecture removes implicit trust based on network location.",
    }
    results, latency = retrieval.search("What is zero trust?")
    assert results[0].chunk_id == "chk_zero_trust"
    assert results[0].tenant_id == settings.tenant_id
    assert latency >= 0


def test_generation_has_citations_metadata_and_persistence(tmp_path: Path) -> None:
    settings, retrieval = build_retrieval(tmp_path)
    response = GenerationService(settings, retrieval=retrieval, llm=FakeLLM()).answer(
        "What is zero trust?"
    )
    assert response.sources[0].page == 4
    assert response.retrieved_chunk_ids[0] == "chk_zero_trust"
    assert response.prompt_version == "rag-v1"
    with retrieval.catalog._connect() as connection:
        row = connection.execute("SELECT * FROM generation_runs").fetchone()
    assert row["prompt_version"] == "rag-v1"
    assert json.loads(row["retrieved_chunk_ids_json"])[0] == "chk_zero_trust"


def test_retrieval_evaluation_metrics(tmp_path: Path) -> None:
    settings, retrieval = build_retrieval(tmp_path)
    dataset = tmp_path / "golden.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "question": "What is zero trust?",
                "expected_document": "NIST-SP-800-207.pdf",
                "expected_pages": [4],
            }
        )
        + "\n"
    )
    report = EvaluationService(settings, retrieval).evaluate_retrieval(dataset)
    assert report["hit_at_1"] == 1
    assert report["hit_at_3"] == 1
    assert report["hit_at_5"] == 1
    assert report["mrr"] == 1
