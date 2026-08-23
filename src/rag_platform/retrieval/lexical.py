from __future__ import annotations

import math
import re
from collections import Counter

from rag_platform.domain.models import ChunkRecord


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_.:/-]+", text.lower())


def bm25_search(query: str, chunks: list[ChunkRecord], limit: int) -> list[tuple[str, float]]:
    if not chunks:
        return []
    documents = [tokenize(chunk.text) for chunk in chunks]
    query_tokens = tokenize(query)
    document_frequency = Counter(token for doc in documents for token in set(doc))
    average_length = sum(map(len, documents)) / len(documents) or 1.0
    scored: list[tuple[str, float]] = []
    for chunk, tokens in zip(chunks, documents, strict=True):
        frequencies = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            frequency = frequencies[token]
            if not frequency:
                continue
            inverse_frequency = math.log(
                1
                + (len(documents) - document_frequency[token] + 0.5)
                / (document_frequency[token] + 0.5)
            )
            denominator = frequency + 1.5 * (1 - 0.75 + 0.75 * len(tokens) / average_length)
            score += inverse_frequency * frequency * 2.5 / denominator
        if score > 0:
            scored.append((chunk.chunk_id, score))
    return sorted(scored, key=lambda item: item[1], reverse=True)[:limit]
