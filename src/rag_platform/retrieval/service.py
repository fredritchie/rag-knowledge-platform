from __future__ import annotations

from time import perf_counter

from rag_platform.config import Settings
from rag_platform.domain.models import ChunkRecord, SearchResult
from rag_platform.domain.state_machine import ensure_transition
from rag_platform.domain.states import DocumentStatus
from rag_platform.retrieval.embeddings import Embedder, build_embedder
from rag_platform.retrieval.lexical import bm25_search
from rag_platform.retrieval.reranker import Reranker, build_reranker
from rag_platform.retrieval.vector_store import (
    QdrantVectorStore,
    VectorHit,
    VectorPoint,
    VectorStore,
)
from rag_platform.storage.sqlite import SQLiteCatalog


class RetrievalService:
    def __init__(
        self,
        settings: Settings,
        *,
        catalog: SQLiteCatalog | None = None,
        embedder: Embedder | None = None,
        vector_store: VectorStore | None = None,
        reranker: Reranker | None = None,
    ):
        self.settings = settings
        self.catalog = catalog or SQLiteCatalog(settings.database_path)
        self.embedder = embedder or build_embedder(settings.embedding)
        self.vector_store = vector_store or QdrantVectorStore(settings.qdrant)
        self.reranker = reranker or build_reranker(settings.reranker)
        self.last_metrics: dict[str, float] = {}

    def index_document(self, document_id: str) -> int:
        document = self.catalog.get_document(document_id)
        if document is None:
            raise ValueError(f"Document not found: {document_id}")
        if document.tenant_id != self.settings.tenant_id:
            raise ValueError(
                f"Document not found for tenant {self.settings.tenant_id}: {document_id}"
            )
        chunks = self.catalog.get_chunks(document_id)
        batch_size = self.settings.embedding.batch_size
        ensure_transition(document.status, DocumentStatus.EMBEDDING)
        self.catalog.update_status(document_id, DocumentStatus.EMBEDDING)
        points: list[VectorPoint] = []
        try:
            for offset in range(0, len(chunks), batch_size):
                batch = chunks[offset : offset + batch_size]
                vectors = self.embedder.embed_documents([chunk.text for chunk in batch])
                points.extend(
                    [
                        VectorPoint(
                            chunk_id=chunk.chunk_id,
                            vector=vector,
                            payload=self._payload(chunk),
                        )
                        for chunk, vector in zip(batch, vectors, strict=True)
                    ]
                )
        except Exception:
            self.catalog.update_status(document_id, DocumentStatus.FAILED_EMBEDDING)
            raise

        self.catalog.update_status(document_id, DocumentStatus.INDEXING)
        try:
            self.vector_store.ensure_collection(self.embedder.dimension)
            for offset in range(0, len(points), batch_size):
                self.vector_store.upsert(points[offset : offset + batch_size])
        except Exception:
            self.catalog.update_status(document_id, DocumentStatus.FAILED_INDEXING)
            raise
        self.catalog.update_status(document_id, DocumentStatus.VALIDATING)
        self.catalog.update_status(document_id, DocumentStatus.ACTIVE)
        return len(chunks)

    def index_all(self) -> tuple[int, int]:
        documents = [
            document
            for document in self.catalog.list_documents(tenant_id=self.settings.tenant_id)
            if document.status
            in {
                DocumentStatus.ACTIVE,
                DocumentStatus.FAILED_EMBEDDING,
                DocumentStatus.FAILED_INDEXING,
            }
        ]
        indexed_chunks = sum(self.index_document(doc.document_id) for doc in documents)
        return len(documents), indexed_chunks

    def search(
        self,
        query: str,
        *,
        top_k: int | None = None,
        mode: str | None = None,
        document_ids: set[str] | None = None,
    ) -> tuple[list[SearchResult], float]:
        started = perf_counter()
        retrieval = self.settings.retrieval
        selected_mode = mode or retrieval.mode
        limit = top_k or retrieval.top_k
        candidate_k = max(limit, retrieval.candidate_k)
        stage_started = perf_counter()
        query_vector = self.embedder.embed_query(query)
        embedding_ms = (perf_counter() - stage_started) * 1000
        stage_started = perf_counter()
        dense_hits = self.vector_store.search(
            query_vector,
            limit=candidate_k,
            tenant_id=self.settings.tenant_id,
            document_ids=document_ids,
            score_threshold=retrieval.similarity_threshold,
        )
        dense_ms = (perf_counter() - stage_started) * 1000
        dense_scores = {hit.chunk_id: hit.score for hit in dense_hits}
        chunk_by_id = {
            chunk.chunk_id: chunk
            for chunk in self.catalog.get_chunks_by_ids(
                [hit.chunk_id for hit in dense_hits], tenant_id=self.settings.tenant_id
            )
        }

        if selected_mode != "dense":
            stage_started = perf_counter()
            all_chunks = self.catalog.get_all_chunks(
                tenant_id=self.settings.tenant_id, document_ids=document_ids
            )
            lexical_hits = bm25_search(query, all_chunks, candidate_k)
            lexical_ms = (perf_counter() - stage_started) * 1000
            lexical_scores = dict(lexical_hits)
            missing_ids = [chunk_id for chunk_id, _ in lexical_hits if chunk_id not in chunk_by_id]
            chunk_by_id.update(
                {
                    chunk.chunk_id: chunk
                    for chunk in self.catalog.get_chunks_by_ids(
                        missing_ids, tenant_id=self.settings.tenant_id
                    )
                }
            )
            stage_started = perf_counter()
            ranked_ids = self._fuse(dense_hits, lexical_hits)
            fusion_ms = (perf_counter() - stage_started) * 1000
        else:
            lexical_scores = {}
            ranked_ids = [(hit.chunk_id, hit.score) for hit in dense_hits]
            lexical_ms = 0.0
            fusion_ms = 0.0

        results = [
            self._result(
                chunk_by_id[chunk_id],
                score=score,
                dense_score=dense_scores.get(chunk_id),
                lexical_score=lexical_scores.get(chunk_id),
            )
            for chunk_id, score in ranked_ids
            if chunk_id in chunk_by_id
        ]
        reranker_ms = 0.0
        if selected_mode == "hybrid_rerank":
            stage_started = perf_counter()
            results = self.reranker.rerank(query, results)
            reranker_ms = (perf_counter() - stage_started) * 1000
        elapsed_ms = (perf_counter() - started) * 1000
        self.last_metrics = {
            "embedding_latency_ms": embedding_ms,
            "dense_latency_ms": dense_ms,
            "lexical_latency_ms": lexical_ms,
            "fusion_latency_ms": fusion_ms,
            "reranker_latency_ms": reranker_ms,
            "retrieval_latency_ms": elapsed_ms,
        }
        return results[:limit], elapsed_ms

    def _fuse(
        self, dense_hits: list[VectorHit], lexical_hits: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        config = self.settings.retrieval
        if config.fusion == "rrf":
            scores: dict[str, float] = {}
            for rank, hit in enumerate(dense_hits, 1):
                scores[hit.chunk_id] = scores.get(hit.chunk_id, 0) + (
                    config.dense_weight / (config.rrf_k + rank)
                )
            for rank, (chunk_id, _) in enumerate(lexical_hits, 1):
                scores[chunk_id] = scores.get(chunk_id, 0) + (
                    config.lexical_weight / (config.rrf_k + rank)
                )
            return sorted(scores.items(), key=lambda item: item[1], reverse=True)

        dense_max = max((hit.score for hit in dense_hits), default=1.0) or 1.0
        lexical_max = max((score for _, score in lexical_hits), default=1.0) or 1.0
        scores = {hit.chunk_id: config.dense_weight * hit.score / dense_max for hit in dense_hits}
        for chunk_id, score in lexical_hits:
            scores[chunk_id] = scores.get(chunk_id, 0) + config.lexical_weight * score / lexical_max
        return sorted(scores.items(), key=lambda item: item[1], reverse=True)

    def _payload(self, chunk: ChunkRecord) -> dict[str, object]:
        return {
            "tenant_id": chunk.tenant_id,
            "document_id": chunk.document_id,
            "document_version": chunk.document_version,
            "source": chunk.source,
            "page": chunk.page,
            "filename": chunk.filename,
            "chunk_index": chunk.chunk_index,
            "embedding_model_version": self.settings.embedding.model_version,
            "chunker_version": chunk.chunker_version,
            "text": chunk.text,
        }

    def _result(
        self,
        chunk: ChunkRecord,
        *,
        score: float,
        dense_score: float | None,
        lexical_score: float | None,
    ) -> SearchResult:
        return SearchResult(
            chunk_id=chunk.chunk_id,
            tenant_id=self.settings.tenant_id,
            document_id=chunk.document_id,
            document_version=chunk.document_version,
            source=chunk.source,
            page=chunk.page,
            filename=chunk.filename,
            chunk_index=chunk.chunk_index,
            embedding_model_version=self.settings.embedding.model_version,
            chunker_version=chunk.chunker_version,
            text=chunk.text,
            score=score,
            dense_score=dense_score,
            lexical_score=lexical_score,
        )
