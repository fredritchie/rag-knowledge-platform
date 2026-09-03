from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from rag_platform.config import EmbeddingSettings


class Embedder(Protocol):
    dimension: int
    model_version: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbedder:
    def __init__(self, config: EmbeddingSettings):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is required for the configured embedding provider; "
                "install with: pip install -e '.[ml]'"
            ) from exc
        self.config = config
        self.model_version = config.model_version
        self._model = SentenceTransformer(config.model, device=config.device)
        self.dimension = int(self._model.get_sentence_embedding_dimension())
        if self.dimension != config.dimension:
            raise ValueError(
                f"Configured embedding dimension {config.dimension} does not match "
                f"model dimension {self.dimension}"
            )

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self.config.batch_size,
            normalize_embeddings=self.config.normalize,
            show_progress_bar=False,
        )
        return [vector.tolist() for vector in vectors]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([self.config.document_prefix + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.config.query_prefix + text])[0]


class DeterministicEmbedder:
    """Offline hashing embedder for tests and plumbing checks, not semantic production search."""

    def __init__(self, config: EmbeddingSettings):
        self.dimension = config.dimension
        self.model_version = config.model_version

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in re.findall(r"[a-z0-9_.:-]+", text.lower()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def build_embedder(config: EmbeddingSettings) -> Embedder:
    if config.provider == "deterministic":
        return DeterministicEmbedder(config)
    return SentenceTransformerEmbedder(config)
