from __future__ import annotations

from typing import Protocol

from rag_platform.config import RerankerSettings
from rag_platform.domain.models import SearchResult


class Reranker(Protocol):
    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]: ...


class NoOpReranker:
    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        return results


class CrossEncoderReranker:
    def __init__(self, config: RerankerSettings):
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError("Install the ML dependencies with: pip install -e '.[ml]'") from exc
        self.config = config
        self._model = CrossEncoder(config.model, device=config.device)

    def rerank(self, query: str, results: list[SearchResult]) -> list[SearchResult]:
        if not results:
            return []
        scores = self._model.predict(
            [(query, result.text) for result in results], batch_size=self.config.batch_size
        )
        updated = [
            result.model_copy(update={"score": float(score), "reranker_score": float(score)})
            for result, score in zip(results, scores, strict=True)
        ]
        return sorted(updated, key=lambda result: result.score, reverse=True)


def build_reranker(config: RerankerSettings) -> Reranker:
    if not config.enabled or config.provider == "none":
        return NoOpReranker()
    return CrossEncoderReranker(config)
