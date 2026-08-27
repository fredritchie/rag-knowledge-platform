from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from rag_platform.config import QdrantSettings


@dataclass(frozen=True, slots=True)
class VectorPoint:
    chunk_id: str
    vector: list[float]
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class VectorHit:
    chunk_id: str
    score: float
    payload: dict[str, Any]


class VectorStore(Protocol):
    def ensure_collection(self, dimension: int) -> None: ...

    def upsert(self, points: list[VectorPoint]) -> None: ...

    def search(
        self,
        vector: list[float],
        *,
        limit: int,
        tenant_id: str,
        document_ids: set[str] | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorHit]: ...

    def delete_document(self, document_id: str, tenant_id: str) -> None: ...

    def delete_document_version(
        self, document_id: str, tenant_id: str, version_id: str
    ) -> None: ...


class QdrantVectorStore:
    def __init__(self, config: QdrantSettings):
        from qdrant_client import QdrantClient

        self.config = config
        self.client = QdrantClient(
            url=config.url,
            api_key=config.api_key,
            timeout=config.timeout_seconds,
            prefer_grpc=config.prefer_grpc,
        )

    def ensure_collection(self, dimension: int) -> None:
        from qdrant_client.models import Distance, PayloadSchemaType, VectorParams

        exists = self.client.collection_exists(self.config.collection)
        if not exists:
            self.client.create_collection(
                collection_name=self.config.collection,
                vectors_config=VectorParams(size=dimension, distance=Distance.COSINE),
            )
            for field in ("tenant_id", "document_id"):
                self.client.create_payload_index(
                    collection_name=self.config.collection,
                    field_name=field,
                    field_schema=PayloadSchemaType.KEYWORD,
                    wait=True,
                )
            return
        vectors = self.client.get_collection(self.config.collection).config.params.vectors
        actual_dimension = getattr(vectors, "size", None)
        if actual_dimension is not None and actual_dimension != dimension:
            raise ValueError(
                f"Qdrant collection dimension is {actual_dimension}, but embedding model "
                f"requires {dimension}; use a new collection name or recreate the collection"
            )

    def upsert(self, points: list[VectorPoint]) -> None:
        from qdrant_client.models import PointStruct

        self.client.upsert(
            collection_name=self.config.collection,
            wait=True,
            points=[
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, point.chunk_id)),
                    vector=point.vector,
                    payload={**point.payload, "chunk_id": point.chunk_id},
                )
                for point in points
            ],
        )

    def search(
        self,
        vector: list[float],
        *,
        limit: int,
        tenant_id: str,
        document_ids: set[str] | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorHit]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        if document_ids is not None and not document_ids:
            return []

        conditions = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        if document_ids is not None:
            conditions.append(
                FieldCondition(key="document_id", match=MatchAny(any=sorted(document_ids)))
            )

        response = self.client.query_points(
            collection_name=self.config.collection,
            query=vector,
            limit=limit,
            score_threshold=score_threshold,
            with_payload=True,
            query_filter=Filter(must=conditions),
        )
        return [
            VectorHit(
                chunk_id=str(point.payload["chunk_id"]),
                score=float(point.score),
                payload=dict(point.payload),
            )
            for point in response.points
        ]

    def delete_document(self, document_id: str, tenant_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        self.client.delete(
            collection_name=self.config.collection,
            wait=True,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                    ]
                )
            ),
        )

    def delete_document_version(self, document_id: str, tenant_id: str, version_id: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

        self.client.delete(
            collection_name=self.config.collection,
            wait=True,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(key="document_id", match=MatchValue(value=document_id)),
                        FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id)),
                        FieldCondition(
                            key="document_version_id", match=MatchValue(value=version_id)
                        ),
                    ]
                )
            ),
        )


class InMemoryVectorStore:
    def __init__(self):
        self.points: dict[str, VectorPoint] = {}
        self.dimension: int | None = None

    def ensure_collection(self, dimension: int) -> None:
        self.dimension = dimension

    def upsert(self, points: list[VectorPoint]) -> None:
        self.points.update({point.chunk_id: point for point in points})

    def search(
        self,
        vector: list[float],
        *,
        limit: int,
        tenant_id: str,
        document_ids: set[str] | None = None,
        score_threshold: float | None = None,
    ) -> list[VectorHit]:
        def cosine(other: list[float]) -> float:
            denominator = math.sqrt(sum(x * x for x in vector)) * math.sqrt(
                sum(x * x for x in other)
            )
            return sum(a * b for a, b in zip(vector, other, strict=True)) / (denominator or 1)

        hits = [
            VectorHit(point.chunk_id, cosine(point.vector), point.payload)
            for point in self.points.values()
            if point.payload.get("tenant_id") == tenant_id
            and (document_ids is None or point.payload.get("document_id") in document_ids)
        ]
        hits = [hit for hit in hits if score_threshold is None or hit.score >= score_threshold]
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]

    def delete_document(self, document_id: str, tenant_id: str) -> None:
        self.points = {
            key: point
            for key, point in self.points.items()
            if not (
                point.payload.get("document_id") == document_id
                and point.payload.get("tenant_id") == tenant_id
            )
        }

    def delete_document_version(self, document_id: str, tenant_id: str, version_id: str) -> None:
        self.points = {
            key: point
            for key, point in self.points.items()
            if not (
                point.payload.get("document_id") == document_id
                and point.payload.get("tenant_id") == tenant_id
                and point.payload.get("document_version_id") == version_id
            )
        }
